"""
Optional LLM understanding layer (OpenAI-compatible APIs, including Groq, OpenRouter and Ollama, or Anthropic).

Design rule: the LLM proposes and the metadata disposes.
  * The LLM only fills a JSON slot schema. Metric names, filter fields and values must come from the
    enumerations given in the prompt.
  * Dates are returned as natural-language phrases and parsed by the deterministic time parser, so the
    LLM never does date arithmetic.
  * Every returned value is checked against the metadata. Anything unknown is dropped and counted as
    a hallucination before planning.

Configure with environment variables (see .env.example):
  LUMEN_AGENT_MODE   rules (default) | hybrid | llm
  LUMEN_LLM_PROVIDER openai | groq | openrouter | ollama | anthropic
  LUMEN_LLM_MODEL    e.g. gpt-4o-mini, llama-3.3-70b-versatile, qwen2.5:7b, claude-haiku-5-5
  LUMEN_LLM_API_KEY  (or OPENAI_API_KEY / GROQ_API_KEY / ANTHROPIC_API_KEY)
  LUMEN_LLM_BASE_URL optional override (e.g. http://localhost:11434/v1 for Ollama)
"""
import json
import os
import re
import time
from urllib.parse import urlsplit

from backend import catalog as C
from backend.nlu import timeparse
from backend.nlu.lexicon import norm
from backend.nlu.parser import ParsedRequest, RuleParser
from backend.semantic.layer import VIEWS

PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
    "ollama": ("http://localhost:11434/v1", None, "qwen2.5:7b-instruct"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "claude-haiku-5-5"),
}
INTENTS = ["show", "navigate", "configure", "query", "compare", "trend", "why", "explain_page", "help", "undo",
           "reset", "save_view", "export", "write_blocked", "greeting"]


def mode():
    return os.environ.get("LUMEN_AGENT_MODE", "rules").lower()


def configured():
    p = os.environ.get("LUMEN_LLM_PROVIDER", "").lower()
    if p not in PROVIDERS:
        return False
    base, key_env, _ = PROVIDERS[p]
    if p == "ollama":
        return True
    return bool(os.environ.get("LUMEN_LLM_API_KEY") or (key_env and os.environ.get(key_env)))


def configuration():
    provider = os.environ.get("LUMEN_LLM_PROVIDER", "").lower()
    base, _, model = PROVIDERS.get(provider, (None, None, None))
    return {"mode": mode(), "configured": configured(), "provider": provider or None,
            "model": os.environ.get("LUMEN_LLM_MODEL", model),
            "endpoint": os.environ.get("LUMEN_LLM_BASE_URL", base),
            "timeout_seconds": os.environ.get("LUMEN_LLM_TIMEOUT", "30"),
            "configuration_only": True}


def catalog_prompt(meta, active_view=None):
    lines = ["METRICS (use exactly view.metric):"]
    for v, spec in VIEWS.items():
        if active_view == "retail" and v != "retail": continue
        if active_view and active_view.startswith("olist_") and not v.startswith("olist_"): continue
        for m, md in spec["metrics"].items():
            lines.append(f"- {v}.{m}: {md['label']} (aka {', '.join(md['synonyms'][:4])})")
    lines.append("\nFILTER FIELDS AND ALLOWED VALUES (use exact spelling):")
    for f, vals in C.DIMENSION_VALUES.items():
        if active_view == "retail" and f not in VIEWS["retail"]["dims"]: continue
        if active_view and active_view.startswith("olist_") and f not in VIEWS[active_view]["dims"]: continue
        lines.append(f"- {f}: {', '.join(vals[:60])}" + (" (sample; ask for exact StockCode if unavailable)" if len(vals) > 60 else ""))
    lines.append("\nPAGES (page_id: title):")
    for pid, p in meta["pages"].items():
        lines.append(f"- {pid}: {p['title']}")
    return "\n".join(lines)


SYSTEM = """You convert a user's request about a business intelligence app into JSON slots.
Return ONLY a JSON object with these keys:
{"intent": one of %s,
 "metric": "view.metric" or null,
 "extra_metrics": ["view.metric", ...],
 "filters": {"field": ["Value", ...]},
 "exclude": {"field": ["Value", ...]},
 "group_by": ["field", ...],
 "time_expression": the time phrase exactly as the user said it (e.g. "last month", "August 2026", "Q3") or null,
 "comparison_expression": the comparison time phrase (e.g. "July", "last year") or null,
 "compare_mode": "previous_period" | "previous_year" | "custom" | "none" | null,
 "sort": {"field": metric-or-field, "dir": "asc"|"desc"} or null,
 "top_n": integer or null,
 "superlative": "highest"|"lowest"|"best"|"worst"|null,
 "page_id": a page_id from the list ONLY if the user names a specific page, else null,
 "is_followup": true if the request depends on the previous turn,
 "clarification_needed": a short question if the request is genuinely ambiguous, else null}
Rules: never invent metrics, fields, values or page ids that are not in the lists. Use "why" for root-cause
questions, "trend" for changes over time, "compare" for X vs Y, "query" for direct questions, "navigate" for
opening pages, "configure" for changing filters/sorting on the current page, and "write_blocked" for any
request to modify or delete data.
Example: "Show South revenue for August 2026" ->
{"intent":"show","metric":"sales.revenue","filters":{"region":["South"]},"time_expression":"August 2026"}
The keys inside filters are actual dimension names such as region; never use the literal key "field".
Dates, months and years belong ONLY in time_expression and comparison_expression, never in filters.
Calendar time buckets are time grain, not business dimensions. Put "monthly" in time_expression rather than "month" in group_by.
Do not list every country as a filter. If no country is explicitly selected, use filters:{}.
Example on the UCI sales page: "Top 5 countries by revenue in 2011" ->
{"intent":"query","metric":"retail.revenue","filters":{},"group_by":["country"],"time_expression":"2011","top_n":5,"sort":{"field":"revenue","dir":"desc"}}
For UCI customer rankings use group_by:["customer_id"]. The identifier is Customer ID; customer names are not present.
For UCI orders use retail.retail_orders, for quantity sold use retail.retail_quantity, and for average order value use retail.retail_aov.
For numerical product contributions use intent:"why", metric:"retail.revenue", group_by:["retail_product"].
Example on the UCI sales page: "Show monthly revenue for 2011" ->
{"intent":"trend","metric":"retail.revenue","filters":{},"group_by":[],"time_expression":"2011 monthly"}
""" % INTENTS


def _post(url, headers, body, timeout=30):
    import httpx
    with httpx.Client(timeout=float(os.environ.get("LUMEN_LLM_TIMEOUT", timeout)),
                      trust_env=urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1")) as c:
        r = c.post(url, headers=headers, json=body)
        if r.status_code == 429:
            provider = os.environ.get("LUMEN_LLM_PROVIDER", "Model").title()
            raise RuntimeError(f"{provider} rate limit (HTTP 429). Wait before retrying or use local Ollama. This turn falls back to rules.")
        r.raise_for_status()
        return r.json()



def slot_schema(active_view=None, text="", ctx=None):
    views = {k:v for k,v in VIEWS.items() if active_view != "retail" or k == "retail"}
    if active_view and active_view.startswith("olist_"): views={k:v for k,v in VIEWS.items() if k.startswith("olist_")}
    metrics = [f"{v}.{m}" for v,s in views.items() for m in s["metrics"]]
    dims = sorted({d for s in views.values() for d in s["dims"]})
    properties = {}
    utterance = " " + norm(text) + " "
    for d in dims:
        allowed = [v for v in C.DIMENSION_VALUES.get(d, []) if " " + norm(v) + " " in utterance]
        allowed += [v for alias,v in C.VALUE_SYNONYMS.get(d, {}).items() if " " + norm(alias) + " " in utterance]
        if re.search(r"\b(it|that|this|same|what about|how about)\b",text,re.I):
            allowed += (ctx or {}).get("filters", {}).get(d, [])
        allowed = sorted(set(allowed))
        properties[d] = ({"type":"array","items":{"type":"string","enum":allowed}}
                         if allowed else {"type":"array","maxItems":0,"items":{"type":"string"}})
    filters = {"type":"object", "properties":properties,"additionalProperties":False}
    nullable_string = {"type":["string","null"]}
    return {"type":"object", "additionalProperties":False,
        "properties":{
            "intent":{"type":"string","enum":INTENTS},
            "metric":{"enum":metrics+[None]},
            "extra_metrics":{"type":"array","items":{"type":"string","enum":metrics}},
            "filters":filters,"exclude":filters,
            "group_by":{"type":"array","items":{"type":"string","enum":dims}},
            "time_expression":nullable_string,"comparison_expression":nullable_string,
            "compare_mode":{"enum":["previous_period","previous_year","custom","none",None]},
            "sort":{"anyOf":[{"type":"null"},{"type":"object","properties":{"field":{"type":"string","enum":list(dict.fromkeys([m for s in views.values() for m in s["metrics"]]+dims))},"dir":{"enum":["asc","desc"]}},"required":["field","dir"],"additionalProperties":False}]},
            "top_n":{"anyOf":[{"type":"null"},{"type":"integer","minimum":1,"maximum":100}]},
            "superlative":{"enum":["highest","lowest","best","worst",None]},
            "page_id":nullable_string,"is_followup":{"type":"boolean"},"clarification_needed":nullable_string},
        "required":["intent","metric","filters","group_by","time_expression","top_n"]}


def call(system, user, schema=None):
    p = os.environ.get("LUMEN_LLM_PROVIDER", "").lower()
    base, key_env, default_model = PROVIDERS[p]
    base = os.environ.get("LUMEN_LLM_BASE_URL", base).rstrip("/")
    model = os.environ.get("LUMEN_LLM_MODEL", default_model)
    key = os.environ.get("LUMEN_LLM_API_KEY") or (os.environ.get(key_env) if key_env else None) or "ollama"
    if p == "anthropic":
        data = _post(f"{base}/messages", {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                     {"model": model, "max_tokens": 700, "temperature": 0, "system": system,
                      "messages": [{"role": "user", "content": user}]})
        text = "".join(b.get("text", "") for b in data.get("content", []))
    else:
        body = {"model": model, "temperature": 0, "messages": [{"role": "system", "content": system},
                                                              {"role": "user", "content": user}]}
        if p in ("openai", "groq", "openrouter", "ollama"):
            body["response_format"] = ({"type":"json_schema","json_schema":{"name":"lumen_slots","schema":schema}}
                                       if p == "ollama" and schema else {"type": "json_object"})
        data = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
        text = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"LLM returned no JSON: {text[:200]}")
    return json.loads(m.group(0))


class LLMUnderstanding:
    def __init__(self, metadata, lexicon):
        self.meta = metadata
        self.lex = lexicon
        self.catalog = catalog_prompt(metadata)
        self.stats = {"calls": 0, "responses": 0, "errors": 0, "hallucinated_slots": 0, "accepted_slots": 0}

    def _value(self, field, value):
        """Snap a proposed value to a real option (exact / case-insensitive / synonym), else None."""
        opts = C.DIMENSION_VALUES.get(field)
        if not opts or value is None:
            return None
        for o in opts:
            if o == value or o.lower() == str(value).lower():
                return o
        syn = C.VALUE_SYNONYMS.get(field, {}).get(norm(str(value)))
        return syn

    def parse(self, text, ctx=None, current_page=None, call_fn=None):
        custom_call = call_fn
        active_view = (ctx or {}).get("view")
        if current_page in self.meta["pages"]: active_view = self.meta["pages"][current_page]["view"]
        if "retail" in VIEWS and re.search(r"\b(uci|online retail ii|real data)\b",text,re.I): active_view="retail"
        if active_view and active_view.startswith("olist_"):
            from backend.nlu.olist import choose_view
            active_view=choose_view(text,active_view)
        if re.search(r"\bolist\b",text,re.I):
            from backend.nlu.olist import choose_view
            active_view=choose_view(text,active_view or "olist_sales")
        catalog = self.catalog
        if hasattr(self, "index"):
            candidates = [pid for pid, _, _ in self.index.search(text, k=12)]
            if current_page in self.meta["pages"] and current_page not in candidates:
                candidates.append(current_page)
            if active_view == "retail": candidates=[pid for pid in self.meta["pages"] if self.meta["pages"][pid]["view"] == "retail"]
            if active_view and active_view.startswith("olist_"): candidates=[pid for pid in self.meta["pages"] if self.meta["pages"][pid]["view"].startswith("olist_")]
            catalog = catalog_prompt({"pages": {pid: self.meta["pages"][pid] for pid in candidates}}, active_view=active_view)
        user = f"{catalog}\n\nCURRENT PAGE: {current_page}\nPREVIOUS TURN CONTEXT: {json.dumps(ctx or {}, default=str)[:800]}\n\nUSER REQUEST: {text}"
        t0 = time.time()
        self.stats["calls"] += 1
        try:
            js = (custom_call(SYSTEM, user) if custom_call else call(SYSTEM, user, schema=slot_schema(active_view, text, ctx)))
            self.stats["responses"] += 1
        except Exception as e:
            self.stats["errors"] += 1
            raise
        pr = ParsedRequest(text=text, normalized=norm(text), source="llm")
        halluc = []
        # Apply request grounding after inference for every provider, including JSON-only Groq.
        grounded = RuleParser(self.meta).parse(text)
        allowed_properties = slot_schema(active_view, text, ctx)["properties"]["filters"]["properties"]
        allowed_values = {field: set(spec["items"].get("enum", [])) for field, spec in allowed_properties.items()}
        for field, values in {**grounded.excluded, **grounded.filters}.items():
            allowed_values.setdefault(field, set()).update(values)
        for field, value in self.meta["pages"].get(current_page, {}).get("presets", {}).items():
            allowed_values.setdefault(field, set()).add(value)
        if js.get("is_followup"):
            for field, values in (ctx or {}).get("filters", {}).items():
                allowed_values.setdefault(field, set()).update(values)
        it = js.get("intent")
        pr.intent = it if it in INTENTS else "show"
        for key in [js.get("metric")] + list(js.get("extra_metrics") or []):
            if not key:
                continue
            if "." in str(key):
                v, m = str(key).split(".", 1)
                if v in VIEWS and m in VIEWS[v]["metrics"]:
                    pr.metrics.append({"view": v, "metric": m, "weak": False, "phrase": "(llm)"})
                    self.stats["accepted_slots"] += 1
                    continue
            halluc.append(f"metric:{key}")
        for src, dst in (("filters", pr.filters), ("exclude", pr.excluded)):
            for f, vals in (js.get(src) or {}).items():
                if f not in C.DIMENSION_VALUES:
                    halluc.append(f"field:{f}")
                    continue
                for val in (vals if isinstance(vals, list) else [vals]):
                    ok = self._value(f, val)
                    if ok and ok not in allowed_values.get(f, set()):
                        halluc.append(f"unrequested:{f}={val}")
                        continue
                    if ok:
                        dst.setdefault(f, [])
                        if ok not in dst[f]:
                            dst[f].append(ok)
                        self.stats["accepted_slots"] += 1
                    else:
                        halluc.append(f"value:{f}={val}")
        temporal_group = None
        for g in js.get("group_by") or []:
            if g in ("day", "week", "month", "quarter"):
                temporal_group = g
                continue
            if g in C.DIMENSION_VALUES:
                pr.group_by.append(g)
            else:
                halluc.append(f"group_by:{g}")
        te, ce = js.get("time_expression"), js.get("comparison_expression")
        phrase = " ".join(x for x in [te, ("vs " + ce) if ce else None] if x)
        from backend.datasets import bounds
        active_view = (ctx or {}).get("view")
        if current_page in self.meta["pages"]: active_view = self.meta["pages"][current_page]["view"]
        pr.time = timeparse.parse(phrase, today=bounds(active_view)[1]) if phrase else timeparse.TimeParse()
        if temporal_group and not pr.time.grain:
            pr.time.grain = temporal_group
        cm = js.get("compare_mode")
        if cm in ("previous_period", "previous_year", "none") and pr.time.compare_mode is None:
            pr.time.compare_mode = cm
        s = js.get("sort")
        if isinstance(s, dict) and s.get("field"):
            pr.sort = {"field": s["field"], "dir": "asc" if s.get("dir") == "asc" else "desc"}
        if isinstance(js.get("top_n"), int):
            pr.top_n = js["top_n"]
        if js.get("superlative") in ("highest", "lowest", "best", "worst"):
            pr.superlative = js["superlative"]
        pid = js.get("page_id")
        if pid:
            if pid in self.meta["pages"]:
                pr.page_mentions = [(pid, 1.0, "(llm)")]
            else:
                halluc.append(f"page:{pid}")
        pr.followup = bool(js.get("is_followup"))
        cq = js.get("clarification_needed")
        if cq:
            pr.clarification_question = str(cq)[:200]
        elif halluc:
            pr.clarification_question = "Some requested fields or values are not available in this app. Please choose a known metric and filter."
        self.stats["hallucinated_slots"] += len(halluc)
        pr.typo_fixes = [("llm_hallucinations_blocked", h) for h in halluc]
        pr.llm_latency_ms = round((time.time() - t0) * 1000)
        pr.llm_blocked = halluc
        return pr
