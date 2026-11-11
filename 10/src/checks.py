import json

import faiss
import numpy as np

from hybrid import HybridSearcher, allowed
from search_lib import DATA, ROOT, average, embedder, encode, load_jsonl, metrics_for, norm

SEED = 42
BOOTSTRAP = 5000
FILTERS = [{"sensitivity": {"public"}}, {"type": {"analytics"}}, {"date_from": "2026-10-01"}]
PROBES = {
    "D04": "план формування та використання фінансових ресурсів",
    "D11": "рівень особистих заощаджень у США",
    "D15": "найліквідніші активи готівка",
    "D22": "облікова ставка центрального банку",
    "D30": "компетентнісні питання онтології",
}


def flat_metrics(model, chunks, queries, max_seq_length=None):
    encoder = embedder(model)
    original = encoder.max_seq_length
    if max_seq_length:
        encoder.max_seq_length = max_seq_length
    emb = encode(model, [c["text"] for c in chunks], "passage")
    encoder.max_seq_length = original
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    _, ids = index.search(encode(model, [q["query"] for q in queries], "query"), 10)
    return average([metrics_for([chunks[i] for i in row], q["answers"]) for row, q in zip(ids, queries)])


def truncation_check(fixed, semantic, queries):
    return {
        "e5_fixed_full": flat_metrics("e5-small", fixed, queries),
        "e5_fixed_truncated_128": flat_metrics("e5-small", fixed, queries, 128),
        "minilm_fixed": flat_metrics("minilm", fixed, queries),
        "e5_semantic": flat_metrics("e5-small", semantic, queries),
        "minilm_semantic": flat_metrics("minilm", semantic, queries),
    }


def spans_check(strategies, queries):
    out = {}
    for name, chunks in strategies.items():
        out[name] = [q["qid"] for q in queries for a in q["answers"]
                     if not any(c["doc_id"] == a["doc_id"] and norm(a["span"]) in norm(c["text"]) for c in chunks)]
    return out


def bootstrap_check():
    per_query = json.loads((ROOT / "docs" / "eval_raw.json").read_text(encoding="utf-8"))["per_query"]
    rng = np.random.default_rng(SEED)
    out = {}
    for metric in ("mrr", "recall@5"):
        delta = np.array([q["hybrid_rerank"][metric] - q["dense"][metric] for q in per_query.values()])
        means = [delta[rng.integers(0, len(delta), len(delta))].mean() for _ in range(BOOTSTRAP)]
        out[metric] = {"delta": round(float(delta.mean()), 3),
                       "ci95": [round(float(v), 3) for v in np.percentile(means, [2.5, 97.5])],
                       "rerank_better": int((delta > 0).sum()), "dense_better": int((delta < 0).sum())}
    return out


def prefilter_check(hs, gold):
    leaks, checks, lost = 0, 0, {}
    for g in gold:
        hnsw_hits = hs.store.search(g["query"], len(hs.chunks))
        for f in FILTERS:
            exact = hs.dense_rank(g["query"], 30, f)
            fused = hs.rrf([hs.bm25_rank(g["query"], 30, f), exact], 30)
            leaks += sum(not allowed(hs.chunks[i], f) for i in fused)
            checks += 1
            old = {hs.pos[c["chunk_id"]] for c in hnsw_hits if allowed(c, f)}
            old_top = [hs.pos[c["chunk_id"]] for c in hnsw_hits if allowed(c, f)][:30]
            key = next(iter(f))
            row = lost.setdefault(key, {"queries": 0, "changed_top30": 0, "max_missing": 0})
            row["queries"] += 1
            row["changed_top30"] += set(old_top) != set(exact)
            row["max_missing"] = max(row["max_missing"], len(set(exact) - old))
    return {"checks": checks, "leaks": leaks, "hnsw_full_k_returned": len(hnsw_hits), "total": len(hs.chunks),
            "old_method_vs_exact": lost}


def update_check(hs, chunks):
    docs = []
    for doc_id, probe in PROBES.items():
        before = {c["doc_id"] for c in hs.search(probe, "hybrid_rerank", 5)}
        removed = hs.delete_doc(doc_id)
        after_delete = {c["doc_id"] for c in hs.search(probe, "hybrid_rerank", 5)}
        new_chunks = [c | {"chunk_id": c["chunk_id"] + "-v2", "text": c["text"] + " [оновлено 2026-10-25]"}
                      for c in chunks if c["doc_id"] == doc_id]
        hs.upsert_doc(doc_id, new_chunks)
        after = hs.search(probe, "hybrid_rerank", 5)
        hit = next((c for c in after if c["doc_id"] == doc_id), None)
        bm25_hits = [hs.chunks[i] for i in hs.bm25_rank(probe, 30)]
        docs.append({"doc_id": doc_id, "in_top5_before": doc_id in before, "removed": removed,
                     "in_top5_after_delete": doc_id in after_delete, "in_top5_after_upsert": hit is not None,
                     "new_version": bool(hit and hit["chunk_id"].endswith("-v2")),
                     "bm25_has_old_version": any(c["doc_id"] == doc_id and not c["chunk_id"].endswith("-v2")
                                                 for c in bm25_hits)})

    store = hs.store
    probe = PROBES["D04"]
    before_ids = [c["chunk_id"] for c in store.search(probe, 5)]
    before_state = {"vectors": store.index.ntotal, "tombstones": len(store.deleted), "live": store.live_count()}
    store.rebuild()
    manual = {"before": before_state,
              "after": {"vectors": store.index.ntotal, "tombstones": len(store.deleted), "live": store.live_count()},
              "same_top5": before_ids == [c["chunk_id"] for c in store.search(probe, 5)]}

    deleted_docs = 0
    for doc_id in sorted({c["doc_id"] for c in hs.chunks}):
        vectors = store.index.ntotal
        hs.delete_doc(doc_id)
        deleted_docs += 1
        if store.index.ntotal < vectors:
            break
    auto = {"docs_deleted": deleted_docs, "vectors_before": vectors, "vectors_after": store.index.ntotal,
            "tombstones_after": len(store.deleted), "live_after": store.live_count(), "searcher_chunks": len(hs.chunks)}
    return {"docs": docs, "manual_rebuild": manual, "auto_rebuild": auto}


def main():
    fixed = load_jsonl(DATA / "chunks_fixed.jsonl")
    structural = load_jsonl(DATA / "chunks_structural.jsonl")
    semantic = load_jsonl(DATA / "chunks_semantic.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    answerable = [g for g in gold if g["answers"]]
    hs = HybridSearcher(fixed)
    out = {
        "spans_unreachable": spans_check({"fixed": fixed, "structural": structural, "semantic": semantic}, answerable),
        "truncation": truncation_check(fixed, semantic, answerable),
        "bootstrap_rerank_vs_dense": bootstrap_check(),
        "prefilter": prefilter_check(hs, gold),
        "update": update_check(hs, fixed),
    }
    (ROOT / "docs" / "checks_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
