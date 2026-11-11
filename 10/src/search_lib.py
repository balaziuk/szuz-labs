import json
import math
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
(ROOT / "docs").mkdir(exist_ok=True)

MODELS = {
    "e5-small": ("intfloat/multilingual-e5-small", "query: ", "passage: "),
    "minilm": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "", ""),
}
RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def load_jsonl(path):
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def save_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("́", "")).strip().lower()


_cache = {}


def embedder(name):
    from sentence_transformers import SentenceTransformer
    if name not in _cache:
        _cache[name] = SentenceTransformer(MODELS[name][0], device="cpu")
    return _cache[name]


def encode(name, texts, kind):
    _, qp, pp = MODELS[name]
    prefix = qp if kind == "query" else pp
    return embedder(name).encode([prefix + t for t in texts], batch_size=32, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False).astype("float32")


TOKEN = re.compile(r"[a-zа-яіїєґ0-9']+", re.I)


def tokenize(text):
    return [t[:6] for t in TOKEN.findall(norm(text)) if len(t) > 1]


def relevant_spans(chunk, answers):
    t = norm(chunk["text"])
    return {i for i, a in enumerate(answers) if a["doc_id"] == chunk["doc_id"] and norm(a["span"]) in t}


def metrics_for(ranked_chunks, answers, ks=(5, 10)):
    n = len(answers)
    out = {}
    for k in ks:
        found = set()
        for c in ranked_chunks[:k]:
            found |= relevant_spans(c, answers)
        out[f"recall@{k}"] = len(found) / n
    rr = 0.0
    for i, c in enumerate(ranked_chunks, start=1):
        if relevant_spans(c, answers):
            rr = 1.0 / i
            break
    out["mrr"] = rr
    covered, dcg = set(), 0.0
    for i, c in enumerate(ranked_chunks[:10], start=1):
        new = relevant_spans(c, answers) - covered
        if new:
            dcg += 1.0 / math.log2(i + 1)
            covered |= new
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(n, 10) + 1))
    out["ndcg@10"] = dcg / idcg
    return out


def average(rows):
    keys = rows[0].keys()
    return {k: round(float(np.mean([r[k] for r in rows])), 3) for k in keys}
