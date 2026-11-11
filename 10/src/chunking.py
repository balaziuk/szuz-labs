import re
import time

import faiss
import numpy as np

from search_lib import DATA, ROOT, average, encode, load_jsonl, metrics_for, save_jsonl

MODEL = "e5-small"
EVAL_QIDS = None


def meta(doc, section):
    return {k: doc[k] for k in ("doc_id", "title", "type", "date", "sensitivity", "source_url")} | {"section": section}


def fixed_chunks(doc, size=120, overlap=30):
    words, owner = [], []
    for sec, paras in doc["sections"]:
        for p in paras:
            for w in p.split():
                words.append(w)
                owner.append(sec)
    out, step = [], size - overlap
    for i, start in enumerate(range(0, max(len(words) - overlap, 1), step), start=1):
        piece = words[start:start + size]
        if len(piece) < 15:
            continue
        out.append(meta(doc, owner[start]) | {"chunk_id": f"{doc['doc_id']}-F{i:03d}", "text": " ".join(piece)})
    return out


def semantic_chunks(doc, max_words=200, min_words=30):
    sents, owner = [], []
    for sec, paras in doc["sections"]:
        for p in paras:
            for s in re.split(r"(?<=[.!?;])\s+", p):
                if s.strip():
                    sents.append(s.strip())
                    owner.append(sec)
    if not sents:
        return []
    emb = encode(MODEL, sents, "passage")
    sims = np.sum(emb[1:] * emb[:-1], axis=1) if len(sents) > 1 else np.array([])
    thr = np.percentile(sims, 25) if len(sims) else 0
    out, cur, cur_sec = [], [sents[0]], owner[0]
    for i in range(1, len(sents)):
        n_words = len(" ".join(cur).split())
        boundary = (sims[i - 1] < thr and n_words >= min_words) or n_words + len(sents[i].split()) > max_words
        if boundary:
            out.append((cur_sec, " ".join(cur)))
            cur, cur_sec = [], owner[i]
        cur.append(sents[i])
    out.append((cur_sec, " ".join(cur)))
    return [meta(doc, sec) | {"chunk_id": f"{doc['doc_id']}-S{i:03d}", "text": t}
            for i, (sec, t) in enumerate(out, start=1) if len(t.split()) >= 10]


def eval_queries(gold, n=10):
    answerable = [g for g in gold if g["answers"]]
    return answerable[::max(1, len(answerable) // n)][:n]


def build_index(chunks):
    t0 = time.perf_counter()
    emb = encode(MODEL, [c["text"] for c in chunks], "passage")
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    return index, time.perf_counter() - t0


def evaluate(index, build_s, chunks, queries):
    q_emb = encode(MODEL, [q["query"] for q in queries], "query")
    _, ids = index.search(q_emb, 10)
    rows, ctx = [], []
    for q, row in zip(queries, ids):
        ranked = [chunks[i] for i in row]
        rows.append(metrics_for(ranked, q["answers"]))
        ctx.append(sum(len(c["text"].split()) for c in ranked[:5]))
    return average(rows) | {"avg_context_words@5": round(float(np.mean(ctx)), 1), "build_s": round(build_s, 1)}


def main():
    docs = load_jsonl(DATA / "documents.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    queries = eval_queries(gold)
    strategies = {
        "fixed": [c for d in docs for c in fixed_chunks(d)],
        "structural": load_jsonl(DATA / "corpus.jsonl"),
        "semantic": [c for d in docs for c in semantic_chunks(d)],
    }
    results = {}
    for name, chunks in strategies.items():
        save_jsonl(DATA / f"chunks_{name}.jsonl", chunks)
        sizes = [len(c["text"].split()) for c in chunks]
        index, build_s = build_index(chunks)
        res = evaluate(index, build_s, chunks, queries)
        full = evaluate(index, build_s, chunks, [g for g in gold if g["answers"]])
        results[name] = {"chunks": len(chunks), "avg_words": round(float(np.mean(sizes)), 1)} | res | {
            f"all_{k}": v for k, v in full.items() if k in ("recall@5", "mrr", "ndcg@10")}
        print(name, results[name])

    md = ["# Р2. Порівняння стратегій chunking\n",
          f"Модель embeddings для всіх стратегій однакова: `{MODEL}` (intfloat/multilingual-e5-small), "
          "індекс FAISS IndexFlatIP (точний пошук за косинусом). Тестові запити (10, keyword і paraphrase, без multihop): "
          + ", ".join(q["qid"] for q in queries) + ".\n",
          "| Стратегія | Фрагментів | Слів у фрагменті (сер.) | recall@5 | recall@10 | MRR | nDCG@10 | "
          "Контекст топ-5, слів | Побудова індексу, с |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n, r in results.items():
        md.append(f"| {n} | {r['chunks']} | {r['avg_words']} | {r['recall@5']} | {r['recall@10']} | {r['mrr']} | "
                  f"{r['ndcg@10']} | {r['avg_context_words@5']} | {r['build_s']} |")
    n_all = sum(1 for g in gold if g["answers"])
    md += ["", f"Перевірка на всіх {n_all} запитах з відповіддю:", "",
           "| Стратегія | recall@5 | MRR | nDCG@10 |", "|---|---|---|---|"]
    for n, r in results.items():
        md.append(f"| {n} | {r['all_recall@5']} | {r['all_mrr']} | {r['all_ndcg@10']} |")
    (ROOT / "docs" / "chunking_raw.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
