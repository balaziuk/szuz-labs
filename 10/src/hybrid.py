import json
import time

import numpy as np
from rank_bm25 import BM25Okapi

from index import VectorStore
from search_lib import DATA, RERANKER, ROOT, embedder, load_jsonl, metrics_for, tokenize

RRF_K = 60
CANDIDATES = 30


def allowed(chunk, filters):
    if not filters:
        return True
    if "type" in filters and chunk["type"] not in filters["type"]:
        return False
    if "sensitivity" in filters and chunk["sensitivity"] not in filters["sensitivity"]:
        return False
    if "date_from" in filters and chunk["date"] < filters["date_from"]:
        return False
    if "date_to" in filters and chunk["date"] > filters["date_to"]:
        return False
    return True


class HybridSearcher:
    def __init__(self, chunks, model="e5-small"):
        self.chunks = list(chunks)
        self.store = VectorStore(model, embedder(model).get_sentence_embedding_dimension())
        self.store.add(self.chunks)
        self._reindex_text()
        self._reranker = None

    def _reindex_text(self):
        self.bm25 = BM25Okapi([tokenize(c["text"] + " " + c["title"]) for c in self.chunks])
        self.pos = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}

    def delete_doc(self, doc_id):
        removed = self.store.delete_doc(doc_id)
        self.chunks = [c for c in self.chunks if c["doc_id"] != doc_id]
        self._reindex_text()
        return removed

    def upsert_doc(self, doc_id, new_chunks):
        removed, added = self.store.upsert_doc(doc_id, new_chunks)
        self.chunks = [c for c in self.chunks if c["doc_id"] != doc_id] + list(new_chunks)
        self._reindex_text()
        return removed, added

    @property
    def reranker(self):
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(RERANKER, device="cpu")
        return self._reranker

    def bm25_rank(self, query, n, filters=None):
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(-scores)
        return [int(i) for i in order if allowed(self.chunks[i], filters)][:n]

    def dense_rank(self, query, n, filters=None):
        if filters:
            hits = self.store.search_filtered(query, n, lambda c: allowed(c, filters))
        else:
            hits = self.store.search(query, n)
        return [self.pos[c["chunk_id"]] for c in hits]

    def rrf(self, lists, n):
        score = {}
        for lst in lists:
            for rank, i in enumerate(lst, start=1):
                score[i] = score.get(i, 0.0) + 1.0 / (RRF_K + rank)
        return [i for i, _ in sorted(score.items(), key=lambda x: -x[1])][:n]

    def rerank(self, query, ids, n):
        scores = self.reranker.predict([(query, self.chunks[i]["text"]) for i in ids], show_progress_bar=False)
        order = np.argsort(-scores)
        return [ids[j] for j in order][:n], [float(scores[j]) for j in order][:n]

    def search(self, query, mode="hybrid_rerank", k=10, filters=None, return_scores=False):
        if mode == "bm25":
            ids, sc = self.bm25_rank(query, k, filters), None
        elif mode == "dense":
            ids, sc = self.dense_rank(query, k, filters), None
        else:
            fused = self.rrf([self.bm25_rank(query, CANDIDATES, filters),
                              self.dense_rank(query, CANDIDATES, filters)], CANDIDATES)
            if mode == "hybrid":
                ids, sc = fused[:k], None
            else:
                ids, sc = self.rerank(query, fused, k)
        res = [self.chunks[i] for i in ids]
        return (res, sc) if return_scores else res


def main():
    chunks = load_jsonl(DATA / "chunks_fixed.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    hs = HybridSearcher(chunks)
    out = {}

    per_q = []
    for g in [g for g in gold if g["answers"]]:
        row = {"qid": g["qid"], "query": g["query"], "type": g["type"]}
        for mode in ("bm25", "dense", "hybrid"):
            ranked = hs.search(g["query"], mode, 10)
            m = metrics_for(ranked, g["answers"])
            row[mode] = {"mrr": m["mrr"], "recall@5": m["recall@5"], "top3": [c["chunk_id"] for c in ranked[:3]]}
        per_q.append(row)
    out["per_query"] = per_q

    examples = []
    for qid in ("Q02", "Q26", "Q57"):
        g = next(x for x in gold if x["qid"] == qid)
        before = hs.search(g["query"], "hybrid", 5)
        after, scores = hs.search(g["query"], "hybrid_rerank", 5, return_scores=True)
        examples.append({"qid": qid, "query": g["query"],
                         "hybrid_top5": [c["chunk_id"] for c in before],
                         "rerank_top5": [c["chunk_id"] for c in after],
                         "rerank_scores": [round(s, 2) for s in scores],
                         "mrr_hybrid": metrics_for(before, g["answers"])["mrr"],
                         "mrr_rerank": metrics_for(after, g["answers"])["mrr"]})
    out["rerank_examples"] = examples

    tests = []
    q = "частка витрат на оренду у фінансовій моделі"
    for title, f in [("без фільтра", None),
                     ("sensitivity = public (зовнішній користувач)", {"sensitivity": {"public"}}),
                     ("type = analytics, sensitivity ⊆ {internal, confidential}",
                      {"type": {"analytics"}, "sensitivity": {"internal", "confidential"}}),
                     ("date_from = 2026-10-01", {"date_from": "2026-10-01"})]:
        res = hs.search(q, "hybrid_rerank", 5, filters=f)
        tests.append({"filter": title, "top5": [(c["chunk_id"], c["type"], c["sensitivity"], c["date"]) for c in res],
                      "all_match": all(allowed(c, f) for c in res)})
    out["prefilter"] = {"query": q, "tests": tests}

    t = time.perf_counter()
    for g in gold[:20]:
        hs.search(g["query"], "hybrid_rerank", 5)
    out["latency_hybrid_rerank_ms"] = round((time.perf_counter() - t) * 1000 / 20, 1)

    (ROOT / "docs" / "hybrid_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for e in examples:
        print(e)
    for t_ in tests:
        print(t_)
    print("latency hybrid+rerank, мс/запит:", out["latency_hybrid_rerank_ms"])


if __name__ == "__main__":
    main()
