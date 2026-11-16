"""Чернетковий перегляд записів llm_log/extract.jsonl зі статусом not_reread.

Для кожного документа порівнює витяг LLM (data/pred_llm.jsonl) із золотою розміткою (data/gold.jsonl)
за типом і межами спану (для зв'язків — ще й суб'єкт/об'єкт) і пише в human_comment, що збіглося,
що модель пропустила і що додала зайвого. Статус стає reviewed, коментар позначено як чернетку
ШІ-асистента — людина має перечитати й виправити.

python src/review_log.py          # показати, що буде записано
python src/review_log.py --apply  # записати в журнал
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "llm_log" / "extract.jsonl"


def key(r):
    k = (r["kind"], r["type"], r["start"], r["end"])
    return k + (r["subject_start"], r["object_start"]) if r["kind"] == "relation" else k


def load(path):
    by_doc = defaultdict(dict)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            by_doc[r["doc_id"]][key(r)] = r
    return by_doc


def label(r):
    if r["kind"] == "relation":
        return f'{r["type"]}({r["subject"]} → {r["object"]})'
    return f'{r["type"]} «{r["text"]}»'


def main():
    gold, pred = load(ROOT / "data" / "gold.jsonl"), load(ROOT / "data" / "pred_llm.jsonl")
    rows = [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    changed = 0
    for r in rows:
        if r.get("human_decision") != "not_reread":
            continue
        g, p = gold[r["doc_id"]], pred[r["doc_id"]]
        hit = g.keys() & p.keys()
        miss = [label(g[k]) for k in sorted(g.keys() - p.keys())]
        extra = [label(p[k]) for k in sorted(p.keys() - g.keys())]
        note = f"[чернетка ШІ-асистента, звірено із gold] збіг {len(hit)}/{len(g)}"
        if miss:
            note += "; пропущено: " + ", ".join(miss)
        if extra:
            note += "; зайве: " + ", ".join(extra)
        if not miss and not extra:
            note += "; розбіжностей немає"
        print(r["doc_id"], note)
        r["human_decision"], r["human_comment"] = "reviewed", note
        changed += 1
    if "--apply" in sys.argv:
        LOG.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"записано {changed} записів")


if __name__ == "__main__":
    main()
