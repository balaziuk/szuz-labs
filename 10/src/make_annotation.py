import csv
import json

from hybrid import HybridSearcher
from search_lib import DATA, ROOT, load_jsonl, relevant_spans

PICK = {"keyword": 4, "paraphrase": 4, "multihop": 2, "no_answer": 2}
PER_QUERY = 6


def main():
    chunks = load_jsonl(DATA / "chunks_fixed.jsonl")
    gold = load_jsonl(ROOT / "eval" / "gold.jsonl")
    hs = HybridSearcher(chunks)
    chosen = []
    for t, n in PICK.items():
        pool = [g for g in gold if g["type"] == t]
        step = max(1, len(pool) // n)
        chosen += pool[::step][:n]

    rows, labels_a = [], {}
    for g in chosen:
        for c in hs.search(g["query"], "hybrid", PER_QUERY):
            rows.append({"item": len(rows) + 1, "qid": g["qid"], "query": g["query"], "chunk_id": c["chunk_id"],
                         "document": c["title"], "fragment": c["text"], "relevant": ""})
            labels_a[f"{g['qid']}|{c['chunk_id']}"] = int(bool(relevant_spans(c, g["answers"])))

    with open(ROOT / "annotation" / "annotation_B.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    (ROOT / "eval" / "annotation_A.json").write_text(json.dumps(labels_a, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    print("запитів:", len(chosen), "пар:", len(rows), "релевантних за A:", sum(labels_a.values()))
    print([g["qid"] for g in chosen])


if __name__ == "__main__":
    main()
