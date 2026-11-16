"""Дедуплікація назв контрагентів: нормалізація, blocking, три порівняння, злиття й unmerge.

Поріг підбирається лише на парах split=dev. Оцінка — на split=test.
"""

import csv
import json
import copy
import math
import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality.llm_judge import judge  # noqa: E402

# Спірна смуга для судді: на dev сюди потрапляють хибна пара «Київстар / Київські комунальні» (0.35)
# і найслабші справжні дублікати (відмінки, 0.60–0.66); впевнені пари (≥ 0.74) суддя не бачить.
BAND = (0.30, 0.70)

RECORDS = [
    ("privat-full", "АТ КБ «ПриватБанк»", "14360570", "privat"),
    ("privat-short", "ПриватБанк", "14360570", "privat"),
    ("privat-talk", "Приват", "", "privat"),
    ("rent-full", "ТОВ «Орендодавець»", "12345678", "rent"),
    ("rent-nom", "Орендодавець", "", "rent"),
    ("rent-case", "орендодавцю", "", "rent"),
    ("silpo-full", "ТОВ «Сільпо-Фуд»", "40720198", "silpo"),
    ("silpo-short", "Сільпо-Фуд", "40720198", "silpo"),
    ("silpo-talk", "сільпо", "", "silpo"),
    ("kyiv-full", "ПрАТ «Київстар»", "21673832", "kyivstar"),
    ("kyiv-short", "Київстар", "", "kyivstar"),
    ("kyiv-talk", "київстар", "", "kyivstar"),
    ("util-full", "АТ «Київські комунальні»", "33445566", "utility"),
    ("util-short", "Київські комунальні", "33445566", "utility"),
    ("util-talk", "комунальні", "", "utility"),
    ("fop-full", "ФОП Іваненко", "99887766", "fop"),
    ("fop-case", "ФОПу Іваненку", "", "fop"),
    ("fop-short", "Іваненко", "", "fop"),
    ("emp-full", "ТОВ «Роботодавець»", "87654321", "employer"),
    ("emp-short", "Роботодавець", "", "employer"),
    ("uklon-full", "ТОВ «Уклон»", "39932340", "uklon"),
    ("uklon-talk", "уклон", "", "uklon"),
    ("anc-full", "ТОВ «Аптека АНЦ»", "36151140", "anc"),
    ("anc-short", "Аптека АНЦ", "", "anc"),
    ("prom-full", "ГО «Прометеус»", "39185340", "prom"),
    ("prom-short", "Прометеус", "", "prom"),
    ("atb-full", "ТОВ «АТБ-Маркет»", "30487219", "atb"),
    ("atb-short", "АТБ-Маркет", "", "atb"),
    ("studio-full", "ТОВ «Діджитал Студіо»", "41122334", "studio"),
    ("studio-short", "Діджитал Студіо", "", "studio"),
]


def norm(text):
    text = text.casefold().replace("«", " ").replace("»", " ")
    text = text.replace("тов", " ").replace("прат", " ").replace("ат", " ").replace("фоп", " ").replace("го", " ")
    text = re.sub(r"[^0-9a-zа-яіїєґ\s]", " ", text)
    return " ".join(text.split())


def tokens(text):
    return [token for token in norm(text).split() if len(token) >= 4]


def string_score(left, right):
    a, b = norm(left), norm(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.92
    # Дайс по символьних трійках
    def grams(value):
        padded = f"  {value} "
        return {padded[i : i + 3] for i in range(len(padded) - 2)}

    ga, gb = grams(a), grams(b)
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def embed(text):
    vector = [0.0] * 64
    folded = norm(text)
    padded = f"  {folded} "
    for index in range(len(padded) - 2):
        gram = padded[index : index + 3]
        # crc32, а не hash(): hash() рядків рандомізується між запусками Python.
        vector[zlib.crc32(gram.encode("utf-8")) % 64] += 1.0
    norm_value = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [item / norm_value for item in vector]


def cosine(left, right):
    return sum(a * b for a, b in zip(embed(left), embed(right)))


def attribute_score(left_code, right_code):
    if left_code and right_code:
        return 1.0 if left_code == right_code else 0.0
    return 0.5


def combined(left, right):
    return (
        0.45 * string_score(left["name"], right["name"])
        + 0.35 * cosine(left["name"], right["name"])
        + 0.20 * attribute_score(left["edrpou"], right["edrpou"])
    )


def blocks(left, right):
    if left["edrpou"] and left["edrpou"] == right["edrpou"]:
        return True
    left_tokens, right_tokens = set(tokens(left["name"])), set(tokens(right["name"]))
    if left_tokens & right_tokens:
        return True
    for token in left_tokens:
        for other in right_tokens:
            if token[:4] == other[:4]:
                return True
    return False


def build_pairs():
    by_cluster = {}
    for record in RECORDS:
        by_cluster.setdefault(record[3], []).append(record[0])
    positives = []
    negatives = []
    records = {record[0]: record for record in RECORDS}
    ids = list(records)
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            same = records[left_id][3] == records[right_id][3]
            (positives if same else negatives).append((left_id, right_id, 1 if same else 0))
    positives.sort()
    negatives.sort()
    # Пари з різним кластером, але спільним початком «київ». Їх легко пропустити blocking-ом.
    hard = [
        ("kyiv-full", "util-full", 0),
        ("kyiv-short", "util-short", 0),
        ("kyiv-talk", "util-talk", 0),
        ("privat-short", "prom-short", 0),
    ]
    hard_keys = {(left, right) for left, right, _label in hard}
    negatives = hard + [row for row in negatives if (row[0], row[1]) not in hard_keys and (row[1], row[0]) not in hard_keys]
    chosen = positives + negatives[: 100 - len(positives)]
    if len(chosen) < 100:
        raise SystemExit(f"пар {len(chosen)}, потрібно щонайменше 100")
    rows = []
    for number, (left_id, right_id, label) in enumerate(chosen):
        rows.append(
            {
                "pair_id": f"p{number:03d}",
                "left_id": left_id,
                "right_id": right_id,
                "label": label,
                "split": "dev" if number % 2 == 0 else "test",
            }
        )
    return rows


def prf(pairs, scores, threshold):
    tp = fp = fn = 0
    for row in pairs:
        predicted = scores[row["pair_id"]] >= threshold
        actual = row["label"] == 1
        if predicted and actual:
            tp += 1
        elif predicted:
            fp += 1
        elif actual:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, tp, fp, fn


def best_threshold(pairs, scores):
    best = (0.5, -1.0)
    grid = [index / 100 for index in range(40, 96)]
    for threshold in grid:
        precision, recall, *_rest = prf(pairs, scores, threshold)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        if f1 > best[1]:
            best = (threshold, f1)
    return best[0]


class UnionFind:
    def __init__(self, ids):
        self.parent = {item: item for item in ids}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left, right):
        self.parent[self.find(left)] = self.find(right)


def main():
    records = {
        record[0]: {"id": record[0], "name": record[1], "edrpou": record[2]}
        for record in RECORDS
    }
    pairs = build_pairs()
    (ROOT / "quality" / "pairs_gold.csv").write_text("", encoding="utf-8")
    with (ROOT / "quality" / "pairs_gold.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pair_id", "left_id", "right_id", "label", "split"])
        writer.writeheader()
        writer.writerows(pairs)
    blocked = []
    for row in pairs:
        if blocks(records[row["left_id"]], records[row["right_id"]]):
            blocked.append(row)
    scores = {}
    for row in pairs:
        if row in blocked or row["pair_id"]:
            left, right = records[row["left_id"]], records[row["right_id"]]
            scores[row["pair_id"]] = combined(left, right) if blocks(left, right) else 0.0
    dev = [row for row in pairs if row["split"] == "dev"]
    test = [row for row in pairs if row["split"] == "test"]
    threshold = best_threshold(dev, scores)
    dev_scores = prf(dev, scores, threshold)
    test_scores = prf(test, scores, threshold)
    # LLM-суддя лише на спірних парах: оцінка в смузі BAND навколо порога (смугу вибрано за dev).
    verdicts = {}
    for row in pairs:
        if BAND[0] <= scores[row["pair_id"]] <= BAND[1]:
            verdict = judge(records[row["left_id"]], records[row["right_id"]], row["pair_id"])
            if verdict and verdict["duplicate"] is not None:
                verdicts[row["pair_id"]] = verdict
    decided = {pid: (1.0 if verdicts[pid]["duplicate"] else 0.0) if pid in verdicts else score for pid, score in scores.items()}
    dev_judged = prf(dev, decided, threshold)
    test_judged = prf(test, decided, threshold)
    final = decided if verdicts else scores
    clusters = UnionFind(records)
    merged = []
    for row in pairs:
        if final[row["pair_id"]] >= threshold:
            clusters.union(row["left_id"], row["right_id"])
            merged.append(row["pair_id"])
    groups = {}
    for record_id in records:
        groups.setdefault(clusters.find(record_id), []).append(record_id)
    state = {
        "threshold": threshold,
        "clusters": {key: value for key, value in groups.items() if len(value) > 1},
        "provenance": {
            record_id: {"name": records[record_id]["name"], "edrpou": records[record_id]["edrpou"]}
            for record_id in records
        },
    }
    # Демонстрація unmerge на копії: кластер Привату знімається, записи повертаються з provenance.
    demo = copy.deepcopy(state["clusters"])
    root = next(key for key, members in demo.items() if "privat-talk" in members)
    restored = demo.pop(root)
    for rid in restored:
        demo[rid] = [rid]
    state["unmerge_demo"] = {
        "at": "2026-11-03",
        "restored_records": [{"id": rid, **state["provenance"][rid]} for rid in restored],
        "clusters_after_unmerge": len(demo),
        "clusters_before_unmerge": len(state["clusters"]),
        "reason": "перевірка, що злиття зворотне; робочі кластери не змінено",
    }
    state["judge"] = {
        pid: {**verdicts[pid], "score": round(scores[pid], 3), "label": next(int(r["label"]) for r in pairs if r["pair_id"] == pid)}
        for pid in verdicts
    }
    (ROOT / "quality" / "merges.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "records": len(records),
        "pairs": len(pairs),
        "blocked": len(blocked),
        "threshold": threshold,
        "dev": {"precision": dev_scores[0], "recall": dev_scores[1]},
        "test": {"precision": test_scores[0], "recall": test_scores[1], "tp": test_scores[2], "fp": test_scores[3], "fn": test_scores[4]},
        "band": BAND,
        "judged_pairs": len(verdicts),
        "dev_with_judge": {"precision": dev_judged[0], "recall": dev_judged[1]},
        "test_with_judge": {"precision": test_judged[0], "recall": test_judged[1], "tp": test_judged[2], "fp": test_judged[3], "fn": test_judged[4]},
        "clusters_final": len(state["clusters"]),
        "unmerged": restored,
    }
    (ROOT / "quality" / "dedup_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"pairs={len(pairs)} blocked={len(blocked)} threshold={threshold:.2f} "
        f"test P={test_scores[0]:.3f} R={test_scores[1]:.3f} | judge on {len(verdicts)} pairs: test P={test_judged[0]:.3f} R={test_judged[1]:.3f} unmerged={restored}"
    )


if __name__ == "__main__":
    main()
