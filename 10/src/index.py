import json
import statistics
import time

import faiss
import numpy as np

from search_lib import DATA, MODELS, ROOT, average, embedder, encode, load_jsonl, metrics_for

HNSW_M = 32
EF_CONSTRUCTION = 200
EF_SEARCH = 64
REBUILD_THRESHOLD = 0.2


class VectorStore:

    def __init__(self, model, dim):
        self.model = model
        self.dim = dim
        self.index = self._new_index()
        self.chunks = []
        self.deleted = set()

    def _new_index(self):
        index = faiss.IndexHNSWFlat(self.dim, HNSW_M, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = EF_CONSTRUCTION
        index.hnsw.efSearch = EF_SEARCH
        return index

    def add(self, chunks):
        emb = encode(self.model, [c["text"] for c in chunks], "passage")
        self.index.add(emb)
        self.chunks += chunks

    def delete_doc(self, doc_id):
        pos = {i for i, c in enumerate(self.chunks) if c["doc_id"] == doc_id and i not in self.deleted}
        self.deleted |= pos
        if len(self.deleted) > REBUILD_THRESHOLD * len(self.chunks):
            self.rebuild()
        return len(pos)

    def upsert_doc(self, doc_id, new_chunks):
        removed = self.delete_doc(doc_id)
        self.add(new_chunks)
        return removed, len(new_chunks)

    def rebuild(self):
        live = [i for i in range(len(self.chunks)) if i not in self.deleted]
        index = self._new_index()
        if live:
            index.add(np.vstack([self.index.reconstruct(i) for i in live]))
        self.index, self.chunks, self.deleted = index, [self.chunks[i] for i in live], set()

    def search(self, query, k=10):
        q = encode(self.model, [query], "query")
        _, ids = self.index.search(q, k + len(self.deleted))
        return [self.chunks[i] for i in ids[0] if i >= 0 and i not in self.deleted][:k]

    def search_filtered(self, query, k, predicate):
        live = [i for i, c in enumerate(self.chunks) if i not in self.deleted and predicate(c)]
        if not live:
            return []
        q = encode(self.model, [query], "query")[0]
        vectors = np.vstack([self.index.reconstruct(i) for i in live])
        order = np.argsort(-(vectors @ q))[:k]
        return [self.chunks[live[j]] for j in order]

    def live_count(self):
        return len(self.chunks) - len(self.deleted)


def eval_queries(gold, n=20):
    answerable = [g for g in gold if g["answers"]]
    return answerable[1::max(1, len(answerable) // n)][:n]


def main():
    chunks = load_jsonl(DATA / "chunks_fixed.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    q20 = eval_queries(gold)
    q_all = [g for g in gold if g["answers"]]
    out = {"params": {"type": "IndexHNSWFlat", "metric": "inner product (cosine)", "M": HNSW_M,
                      "efConstruction": EF_CONSTRUCTION, "efSearch": EF_SEARCH, "chunks": len(chunks),
                      "eval20": [q["qid"] for q in q20]}, "models": {}}
    stores = {}
    for name in MODELS:
        emb_model = embedder(name)
        tok = emb_model.tokenizer
        lens = [len(tok(c["text"])["input_ids"]) for c in chunks]
        truncated = sum(n > emb_model.max_seq_length for n in lens)

        t0 = time.perf_counter()
        store = VectorStore(name, emb_model.get_sentence_embedding_dimension())
        store.add(chunks)
        build_s = time.perf_counter() - t0
        stores[name] = store
        (ROOT / "index" / f"{name}.faiss").write_bytes(faiss.serialize_index(store.index).tobytes())
        (ROOT / "index" / f"{name}_ids.json").write_text(
            json.dumps([c["chunk_id"] for c in store.chunks]), encoding="utf-8")

        def run(queries):
            rows, lat = [], []
            for q in queries:
                t = time.perf_counter()
                ranked = store.search(q["query"], 10)
                lat.append((time.perf_counter() - t) * 1000)
                rows.append(metrics_for(ranked, q["answers"]))
            return average(rows), round(statistics.median(lat), 1), round(float(np.percentile(lat, 95)), 1)

        m20, lat_med, lat_p95 = run(q20)
        m_all, _, _ = run(q_all)
        by_type = {}
        for t in ("keyword", "paraphrase", "multihop"):
            qs = [q for q in q_all if q["type"] == t]
            by_type[t] = run(qs)[0]["recall@5"]
        out["models"][name] = {
            "hf_name": MODELS[name][0], "dim": emb_model.get_sentence_embedding_dimension(),
            "max_seq_length": emb_model.max_seq_length,
            "median_tokens": int(statistics.median(lens)), "truncated_chunks": truncated,
            "build_s": round(build_s, 1), "latency_ms_median": lat_med, "latency_ms_p95": lat_p95,
            "eval20": m20, "all": m_all, "recall@5_by_type": by_type,
        }
        print(name, json.dumps(out["models"][name], ensure_ascii=False))

    store = stores["e5-small"]
    test_docs = ["D04", "D11", "D15", "D22", "D30"]
    probes = {
        "D04": "план формування та використання фінансових ресурсів",
        "D11": "рівень особистих заощаджень у США",
        "D15": "найліквідніші активи готівка",
        "D22": "облікова ставка центрального банку",
        "D30": "компетентнісні питання онтології",
    }
    log = []
    before = store.live_count()
    for d in test_docs:
        top_before = store.search(probes[d], 5)
        in_before = any(c["doc_id"] == d for c in top_before)
        n_del = store.delete_doc(d)
        top_after_del = store.search(probes[d], 5)
        in_after_del = any(c["doc_id"] == d for c in top_after_del)
        new_chunks = [c | {"chunk_id": c["chunk_id"] + "-v2", "text": c["text"] + " [оновлено 2026-10-25]"}
                      for c in chunks if c["doc_id"] == d]
        _, n_add = store.upsert_doc(d, new_chunks)
        top_after_up = store.search(probes[d], 5)
        hit = next((c for c in top_after_up if c["doc_id"] == d), None)
        log.append({"doc_id": d, "probe": probes[d], "in_top5_before": in_before, "deleted_chunks": n_del,
                    "in_top5_after_delete": in_after_del, "upserted_chunks": n_add,
                    "in_top5_after_upsert": hit is not None,
                    "new_version_returned": bool(hit and hit["chunk_id"].endswith("-v2"))})
        print(log[-1])
    out["update_test"] = {"live_before": before, "live_after": store.live_count(),
                          "faiss_vectors_after": store.index.ntotal, "tombstones": len(store.deleted),
                          "docs": log}
    (ROOT / "docs" / "embeddings_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")


if __name__ == "__main__":
    main()
