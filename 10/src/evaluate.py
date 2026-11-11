import json
import statistics
import time

import numpy as np

from hybrid import HybridSearcher
from search_lib import DATA, ROOT, average, load_jsonl, metrics_for

CONFIGS = ["bm25", "dense", "hybrid", "hybrid_rerank"]


def main():
    chunks = load_jsonl(DATA / "chunks_fixed.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    answerable = [g for g in gold if g["answers"]]
    no_answer = [g for g in gold if not g["answers"]]
    hs = HybridSearcher(chunks)
    hs.search("прогрів", "hybrid_rerank", 5)

    out = {"n_answerable": len(answerable), "n_no_answer": len(no_answer), "configs": {}, "per_query": {}}
    for cfg in CONFIGS:
        rows, lat, by_type = [], [], {}
        for g in answerable:
            t = time.perf_counter()
            ranked = hs.search(g["query"], cfg, 10)
            lat.append((time.perf_counter() - t) * 1000)
            m = metrics_for(ranked, g["answers"])
            rows.append(m)
            by_type.setdefault(g["type"], []).append(m)
            out["per_query"].setdefault(g["qid"], {})[cfg] = {k: round(v, 3) for k, v in m.items()}
        out["configs"][cfg] = average(rows) | {
            "latency_ms_median": round(statistics.median(lat), 1),
            "latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
            "by_type": {t: average(v)["recall@5"] for t, v in by_type.items()},
        }
        print(cfg, json.dumps(out["configs"][cfg], ensure_ascii=False))

    def top_score(q):
        _, sc = hs.search(q, "hybrid_rerank", 1, return_scores=True)
        return sc[0]
    ans_scores = [top_score(g["query"]) for g in answerable]
    na_scores = [top_score(g["query"]) for g in no_answer]
    out["no_answer"] = {
        "answerable_top1_score": {"median": round(statistics.median(ans_scores), 2),
                                  "p10": round(float(np.percentile(ans_scores, 10)), 2),
                                  "min": round(min(ans_scores), 2)},
        "no_answer_top1_scores": {g["qid"]: round(s, 2) for g, s in zip(no_answer, na_scores)},
    }
    thr = 0.0
    out["no_answer"]["threshold"] = thr
    out["no_answer"]["no_answer_rejected"] = sum(s < thr for s in na_scores)
    out["no_answer"]["answerable_wrongly_rejected"] = sum(s < thr for s in ans_scores)
    print(json.dumps(out["no_answer"], ensure_ascii=False))
    (ROOT / "docs" / "eval_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
