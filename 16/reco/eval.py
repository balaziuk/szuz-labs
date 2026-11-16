"""Офлайн-оцінка. Test-кліки не входять у популярність, профіль і центроїд."""

import json
import math
import random
from collections import defaultdict
from pathlib import Path

from reco.data import ROOT, allowed
from reco.recommend import by_user, recommend

CONFIGS = ("popularity", "graph", "knn", "hybrid")
BOOTSTRAP = 400


def _dcg(flags):
    return sum(flag / math.log2(index + 1) for index, flag in enumerate(flags, start=1))


def _user_metrics(ranking, relevant):
    top5 = ranking[:5]
    top10 = ranking[:10]
    hits5 = sum(1 for doc_id in top5 if doc_id in relevant)
    flags = [1.0 if doc_id in relevant else 0.0 for doc_id in top10]
    ideal = _dcg([1.0] * min(len(relevant), 10))
    return {
        "p5": hits5 / 5,
        "r5": hits5 / len(relevant),
        "ndcg10": (_dcg(flags) / ideal) if ideal else 0.0,
    }


def evaluate(docs, rows):
    train_counts = defaultdict(int)
    for row in rows:
        if row["split"] == "train":
            train_counts[row["doc"]] += 1
    test = by_user(rows, "test")
    per_user = {name: [] for name in CONFIGS}
    recommended = {name: set() for name in CONFIGS}
    universe = {doc_id for doc_id, doc in docs.items() if allowed(doc)}
    used = 0
    for user, docs_clicked in sorted(test.items()):
        relevant = {doc_id for doc_id in docs_clicked if allowed(docs[doc_id])}
        if not relevant:
            continue
        used += 1
        result = recommend(docs, rows, user)
        for name in CONFIGS:
            ranking = result["lists"][name]
            per_user[name].append(_user_metrics(ranking, relevant))
            recommended[name].update(ranking[:5])
    total_train = sum(train_counts.values()) or 1
    summary = {}
    for name in CONFIGS:
        rows_m = per_user[name]
        count = len(rows_m) or 1
        novelty_values = []
        for doc_id in recommended[name]:
            probability = (train_counts[doc_id] + 1) / (total_train + 1)
            novelty_values.append(-math.log2(probability))
        summary[name] = {
            "p5": sum(row["p5"] for row in rows_m) / count,
            "r5": sum(row["r5"] for row in rows_m) / count,
            "ndcg10": sum(row["ndcg10"] for row in rows_m) / count,
            "coverage": len(recommended[name]) / len(universe),
            "novelty": sum(novelty_values) / len(novelty_values),
        }
    intervals = {name: _bootstrap(per_user[name]) for name in ("popularity", "graph", "hybrid")}
    chosen = max(CONFIGS, key=lambda name: (summary[name]["ndcg10"], summary[name]["coverage"]))
    sample_user = sorted(by_user(rows, "train"))[0]
    public = recommend(docs, rows, sample_user, role="public", verified_only=False)
    analyst = recommend(docs, rows, sample_user, role="analyst", verified_only=False)
    strict = recommend(docs, rows, sample_user, role="analyst", verified_only=True)
    filters = {
        "user": sample_user,
        "d22_public": "d22" in public["lists"]["hybrid"],
        "d22_analyst": "d22" in analyst["lists"]["hybrid"],
        "d20_strict": "d20" in strict["lists"]["hybrid"],
        "d22_strict": "d22" in strict["lists"]["hybrid"],
    }
    report = {
        "users_evaluated": used,
        "candidate_items": len(universe),
        "configs": summary,
        "ndcg_ci95": intervals,
        "chosen": chosen,
        "rrf_k": 60,
        "filters": filters,
    }
    path = ROOT / "data" / "metrics.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _markdown(report)
    return report


def _bootstrap(rows_m):
    rng = random.Random(42)
    means = []
    size = len(rows_m)
    for _ in range(BOOTSTRAP):
        sample = [rows_m[rng.randrange(size)]["ndcg10"] for _ in range(size)]
        means.append(sum(sample) / size)
    means.sort()
    low = means[int(0.025 * (BOOTSTRAP - 1))]
    high = means[int(0.975 * (BOOTSTRAP - 1))]
    return {"low": low, "high": high, "repeats": BOOTSTRAP}


def _markdown(report):
    lines = [
        "# Офлайн-оцінка рекомендацій",
        "",
        "Користувачів 60, усі синтетичні, seed 42. Клік має дату не раніше за документ і не пізніше 2026-10-20.",
        "Train: дата кліку < 2026-08-01. Test: дата ≥ 2026-08-01. Популярність, профіль графа й центроїд триграм рахуються лише з train.",
        "Кандидат відсіюється, якщо це нотатка (`verified`) або дата документа раніше 2026-02-01 (`свіжість`). Релевантним вважається test-клік, який пройшов ті самі фільтри.",
        "Embedding — хеш символьних триграм у 64 виміри, не нейромережа. Гібрид — RRF з k=60 по трьох списках.",
        "",
        f"Користувачів у розрахунку: {report['users_evaluated']}. Кандидатів після фільтрів: {report['candidate_items']}.",
        "",
        "| конфігурація | P@5 | R@5 | nDCG@10 | coverage | novelty |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, metrics in report["configs"].items():
        lines.append(
            "| {name} | {p5:.3f} | {r5:.3f} | {ndcg10:.3f} | {coverage:.3f} | {novelty:.3f} |".format(name=name, **metrics)
        )
    pop = report["ndcg_ci95"]["popularity"]
    graph = report["ndcg_ci95"]["graph"]
    hybrid = report["ndcg_ci95"]["hybrid"]
    lines += [
        "",
        f"95% інтервал nDCG@10, бутстреп користувачів, {pop['repeats']} повторів, seed 42.",
        f"Популярність: {pop['low']:.3f}–{pop['high']:.3f}. Граф: {graph['low']:.3f}–{graph['high']:.3f}. Гібрид: {hybrid['low']:.3f}–{hybrid['high']:.3f}.",
        "",
        f"Обрана конфігурація: {report['chosen']}. Критерій — більший nDCG@10, за рівності більший coverage.",
        "Якщо інтервали популярності й гібрида перетинаються, різниця середніх не відділена цим бутстрепом.",
        "",
        "## Фільтри",
        "",
        f"Користувач {report['filters']['user']}.",
        f"d22 у списку public без фільтра verified: {report['filters']['d22_public']}.",
        f"d22 у списку analyst без фільтра verified: {report['filters']['d22_analyst']}.",
        f"d22 у звичайному списку (verified і свіжість): {report['filters']['d22_strict']}.",
        f"d20 (дата 2026-01-15) у звичайному списку: {report['filters']['d20_strict']}.",
        "",
    ]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "reco_eval.md").write_text("\n".join(lines), encoding="utf-8")
