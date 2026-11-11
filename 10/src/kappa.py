import csv
import json

from search_lib import ROOT


def cohen_kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, po, pe


def main():
    labels_a = json.loads((ROOT / "eval" / "annotation_A.json").read_text(encoding="utf-8"))
    with open(ROOT / "annotation" / "annotation_B.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    missing = [r["item"] for r in rows if r["relevant"].strip() not in ("0", "1")]
    if missing:
        raise SystemExit(f"не заповнено або не 0/1: рядки {missing[:20]}")
    a = [labels_a[f"{r['qid']}|{r['chunk_id']}"] for r in rows]
    b = [int(r["relevant"]) for r in rows]
    kappa, po, pe = cohen_kappa(a, b)
    matrix = {"A1_B1": sum(x == 1 and y == 1 for x, y in zip(a, b)),
              "A1_B0": sum(x == 1 and y == 0 for x, y in zip(a, b)),
              "A0_B1": sum(x == 0 and y == 1 for x, y in zip(a, b)),
              "A0_B0": sum(x == 0 and y == 0 for x, y in zip(a, b))}
    by_query = {}
    for r, x, y in zip(rows, a, b):
        by_query.setdefault(r["qid"], {"query": r["query"], "agree": 0, "n": 0})
        by_query[r["qid"]]["agree"] += x == y
        by_query[r["qid"]]["n"] += 1
    disagreements = [{"qid": r["qid"], "query": r["query"], "chunk_id": r["chunk_id"], "A": x, "B": y,
                      "fragment": r["fragment"][:300]} for r, x, y in zip(rows, a, b) if x != y]
    out = {"pairs": len(rows), "queries": len(by_query), "kappa": round(kappa, 3), "observed_agreement": round(po, 3),
           "expected_agreement": round(pe, 3), "matrix": matrix, "by_query": by_query,
           "disagreements": disagreements}
    (ROOT / "docs" / "kappa_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("disagreements", "by_query")}, ensure_ascii=False))
    print("розбіжностей:", len(disagreements))


if __name__ == "__main__":
    main()
