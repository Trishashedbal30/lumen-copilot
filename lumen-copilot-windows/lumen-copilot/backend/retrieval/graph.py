"""
Knowledge graph of the application: directories, subdirectories, pages, widgets, data views, metrics,
dimensions, filter fields and preset values, plus cross-view causal links.

The planner uses it for structured lookups ("which pages show churn_rate filtered to Premium?"), and the
cause engine uses it to find related views. It is also served at /api/graph for the visual explorer.
"""
from collections import defaultdict

from backend import catalog as C
from backend.semantic.layer import VIEWS, VIEW_LINKS


class AppGraph:
    def __init__(self, metadata):
        self.meta = metadata
        self.nodes = {}
        self.edges = []
        self.out = defaultdict(list)
        self.inn = defaultdict(list)
        self._build()
        # fast indexes
        self.pages_by_metric = defaultdict(set)
        self.pages_by_view = defaultdict(set)
        self.pages_by_preset = defaultdict(set)
        self.pages_by_breakdown = defaultdict(set)
        for pid, p in metadata["pages"].items():
            self.pages_by_view[p["view"]].add(pid)
            for w in p["widgets"]:
                for m in ([w["metric"]] if "metric" in w else w.get("metrics", [])):
                    self.pages_by_metric[(w["view"], m)].add(pid)
            for f, v in p.get("presets", {}).items():
                self.pages_by_preset[(f, v)].add(pid)
            for b in p.get("breakdowns", []):
                self.pages_by_breakdown[b].add(pid)

    def node(self, nid, ntype, label, **attrs):
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "type": ntype, "label": label, **attrs}

    def edge(self, a, b, rel):
        self.edges.append({"source": a, "target": b, "rel": rel})
        self.out[a].append((b, rel))
        self.inn[b].append((a, rel))

    def _build(self):
        m = self.meta
        for view, spec in VIEWS.items():
            self.node(f"view:{view}", "view", spec["label"])
            for met, md in spec["metrics"].items():
                self.node(f"metric:{view}.{met}", "metric", md["label"])
                self.edge(f"view:{view}", f"metric:{view}.{met}", "has_metric")
            for d in spec["dims"]:
                self.node(f"dim:{d}", "dimension", C.DIMENSION_LABELS[d])
                self.edge(f"view:{view}", f"dim:{d}", "has_dimension")
        for a, b, mapping, label in VIEW_LINKS:
            self.edge(f"view:{a}", f"view:{b}", f"related:{label}")
        for d in m["directories"]:
            self.node(f"dir:{d['id']}", "directory", d["label"])
            for s in d["subdirectories"]:
                self.node(f"sub:{s['id']}", "subdirectory", s["label"])
                self.edge(f"dir:{d['id']}", f"sub:{s['id']}", "contains")
                for pid in s["pages"]:
                    p = m["pages"][pid]
                    self.node(f"page:{pid}", "page", p["title"], route=p["route"])
                    self.edge(f"sub:{s['id']}", f"page:{pid}", "contains")
                    self.edge(f"page:{pid}", f"view:{p['view']}", "primary_view")
                    for f in p["filters"]:
                        self.edge(f"page:{pid}", f"dim:{f['field']}", "filterable_by")
                    for f, v in p.get("presets", {}).items():
                        self.node(f"value:{f}={v}", "value", v, field=f)
                        self.edge(f"page:{pid}", f"value:{f}={v}", "preset")
                        self.edge(f"value:{f}={v}", f"dim:{f}", "value_of")
                    for w in p["widgets"]:
                        wid = f"widget:{w['id']}"
                        self.node(wid, "widget", w["title"], wtype=w["type"])
                        self.edge(f"page:{pid}", wid, "has_widget")
                        for met in ([w["metric"]] if "metric" in w else w.get("metrics", [])):
                            self.edge(wid, f"metric:{w['view']}.{met}", "shows")
                        if w.get("dimension"):
                            self.edge(wid, f"dim:{w['dimension']}", "breaks_down_by")

    # ------------------------------------------------------------------
    def related_views(self, view):
        return [(b, mapping, label) for a, b, mapping, label in VIEW_LINKS if a == view]

    def stats(self):
        counts = defaultdict(int)
        for n in self.nodes.values():
            counts[n["type"]] += 1
        return {"nodes": len(self.nodes), "edges": len(self.edges), "by_type": dict(counts)}

    def export(self, max_widgets=False):
        nodes = [n for n in self.nodes.values() if max_widgets or n["type"] != "widget"]
        keep = {n["id"] for n in nodes}
        edges = [e for e in self.edges if e["source"] in keep and e["target"] in keep]
        return {"nodes": nodes, "edges": edges, "stats": self.stats()}
