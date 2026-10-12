"""
Retrieval over application metadata.

Rankers:
  * BM25 over word tokens (exact names, metric words)
  * TF-IDF character n-gram vectors (typos, partial words, morphology)
  * optional dense sentence embeddings (set LUMEN_DENSE=1 and pip install sentence-transformers)
Scores are min-max normalised and fused. The planner then re-ranks the candidates with structured
signals from the knowledge graph (see backend/agent/planner.py).
"""
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from backend import catalog as C
from backend.nlu.lexicon import norm
from backend.semantic.layer import VIEWS


def stem(t):
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def tokenize(s):
    return [stem(t) for t in norm(s).split() if t not in {"the", "and", "of", "a", "an", "by", "for", "in", "to", "me", "show"}]


def page_document(p):
    v = VIEWS[p["view"]]
    metric_words = []
    for m in p["primary_metrics"]:
        md = v["metrics"].get(m)
        if md:
            metric_words.append(md["label"])
            metric_words.extend(md["synonyms"][:4])
    widget_titles = [w["title"] for w in p["widgets"]]
    presets = [f"{C.DIMENSION_LABELS[k]} {val}" for k, val in p.get("presets", {}).items()]
    parts = [p["title"]] * 3 + [" ".join(p["breadcrumb"])] + p.get("synonyms", []) * 2 + [p["description"]] + \
        widget_titles + metric_words + presets + [v["label"]]
    return " . ".join(parts)


class BM25:
    def __init__(self, docs, k1=1.4, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(1, self.N)
        self.tf = [Counter(d) for d in self.docs]
        df = defaultdict(int)
        for d in self.docs:
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query):
        q = tokenize(query)
        out = np.zeros(self.N)
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[i] = s
        return out


class MetadataIndex:
    def __init__(self, metadata):
        self.meta = metadata
        self.page_ids = list(metadata["pages"].keys())
        self.docs = [page_document(metadata["pages"][pid]) for pid in self.page_ids]
        self.bm25 = BM25(self.docs)
        self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self.tfidf_m = self.tfidf.fit_transform([norm(d) for d in self.docs])
        self.dense = None
        if os.environ.get("LUMEN_DENSE") == "1":
            try:
                from sentence_transformers import SentenceTransformer
                name = os.environ.get("LUMEN_DENSE_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
                self.dense_model = SentenceTransformer(name)
                self.dense = self.dense_model.encode(self.docs, normalize_embeddings=True)
            except Exception as e:  # optional component
                print(f"[retrieval] dense embeddings disabled: {e}")
                self.dense = None

    @staticmethod
    def _mm(x):
        x = np.asarray(x, dtype=float)
        hi = x.max() if len(x) else 0
        return x / hi if hi > 0 else x

    def search(self, query, k=25, mode="hybrid"):
        """mode: bm25 | tfidf | dense | hybrid"""
        comps = {}
        if mode in ("bm25", "hybrid"):
            comps["bm25"] = self._mm(self.bm25.scores(query))
        if mode in ("tfidf", "hybrid"):
            qv = self.tfidf.transform([norm(query)])
            comps["tfidf"] = self._mm((self.tfidf_m @ qv.T).toarray().ravel())
        if mode in ("dense", "hybrid") and self.dense is not None:
            qe = self.dense_model.encode([query], normalize_embeddings=True)[0]
            comps["dense"] = self._mm(self.dense @ qe)
        if not comps:
            return []
        weights = {"bm25": 0.55, "tfidf": 0.45, "dense": 0.5}
        total = sum(weights[c] * v for c, v in comps.items()) / sum(weights[c] for c in comps)
        order = np.argsort(-total)[:k]
        return [(self.page_ids[i], float(total[i]), {c: round(float(v[i]), 3) for c, v in comps.items()}) for i in order]
