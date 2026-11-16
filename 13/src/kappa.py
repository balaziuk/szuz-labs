"""κ Коена для двох проходів розмітки одних і тих самих спанів.

python src/kappa.py                         — прохід А (gold) проти проходу В (data/annotator_b.jsonl)
python src/kappa.py --blank                 — бланк data/kappa_blank.csv для незалежного розмітника (без золотих міток)
python src/kappa.py --from data/kappa_c.csv [--annotator "хто"] — κ золотих міток проти заповненого бланка -> data/kappa_independent.json
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cohen_kappa(labels_a, labels_b):
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("обидва списки міток мають бути однакової ненульової довжини")
    labels = sorted(set(labels_a) | set(labels_b))
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for left, right in zip(labels_a, labels_b):
        matrix[index[left]][index[right]] += 1
    n = len(labels_a)
    observed = sum(matrix[i][i] for i in range(len(labels))) / n
    expected = 0.0
    for i in range(len(labels)):
        row = sum(matrix[i]) / n
        col = sum(matrix[j][i] for j in range(len(labels))) / n
        expected += row * col
    kappa = 1.0 if expected == 1 else (observed - expected) / (1 - expected)
    return {
        "n": n,
        "labels": labels,
        "observed_agreement": round(observed, 4),
        "expected_agreement": round(expected, 4),
        "kappa": round(kappa, 4),
        "disagreements": n - sum(matrix[i][i] for i in range(len(labels))),
        "confusion": {
            labels[i]: {labels[j]: matrix[i][j] for j in range(len(labels)) if matrix[i][j]}
            for i in range(len(labels))
        },
    }


def main():
    gold = {}
    with (ROOT / "data" / "gold.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "entity":
                gold[row["id"]] = row
    pairs = []
    with (ROOT / "data" / "annotator_b.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            pairs.append((gold[row["id"]]["type"], row["label"], row))
    stats = cohen_kappa([item[0] for item in pairs], [item[1] for item in pairs])
    stats["items"] = [
        {
            "id": row["id"],
            "text": row["text"],
            "a": left,
            "b": right,
        }
        for left, right, row in pairs
        if left != right
    ]
    destination = ROOT / "data" / "kappa.json"
    destination.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"kappa={stats['kappa']} n={stats['n']} "
        f"po={stats['observed_agreement']} disagreements={stats['disagreements']}"
    )
    return stats


LABELS = "Account, Amount, Category, Counterparty, Currency, Date, Edrpou, Period, Risk, O (не сутність)"


def _sample():
    gold = {}
    with (ROOT / "data" / "gold.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "entity":
                gold[row["id"]] = row
    with (ROOT / "data" / "annotator_b.jsonl").open(encoding="utf-8") as handle:
        ids = [json.loads(line)["id"] for line in handle if line.strip()]
    return gold, ids


def blank():
    gold, ids = _sample()
    path = ROOT / "data" / "kappa_blank.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "контекст", "спан", f"мітка ({LABELS})"])
        for span_id in ids:
            row = gold[span_id]
            text = (ROOT / "data" / "docs" / f"{row['doc_id']}.txt").read_text(encoding="utf-8")
            left, right = max(0, row["start"] - 50), min(len(text), row["end"] + 50)
            context = text[left:row["start"]] + "[[" + text[row["start"]:row["end"]] + "]]" + text[row["end"]:right]
            writer.writerow([span_id, " ".join(context.split()), row["text"], ""])
    print(f"{path} — {len(ids)} спанів; інструкція: docs/extraction_schema.md")


def independent(path):
    gold, _ids = _sample()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.reader(handle)][1:]
    labelled = [(r[0], r[3].strip().split()[0]) for r in rows if len(r) > 3 and r[3].strip()]
    stats = cohen_kappa([gold[i]["type"] for i, _ in labelled], [label for _, label in labelled])
    stats["source"] = Path(path).name
    stats["annotator"] = sys.argv[sys.argv.index("--annotator") + 1] if "--annotator" in sys.argv else "не вказано"
    stats["items"] = [{"id": i, "text": gold[i]["text"], "a": gold[i]["type"], "c": label} for i, label in labelled if gold[i]["type"] != label]
    (ROOT / "data" / "kappa_independent.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"independent kappa={stats['kappa']} n={stats['n']} po={stats['observed_agreement']} disagreements={stats['disagreements']}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--blank"]:
        blank()
    elif sys.argv[1:2] == ["--from"]:
        independent(sys.argv[2])
    else:
        main()
