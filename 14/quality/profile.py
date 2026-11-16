"""Базовий профіль якості сховища ЛР8–9.

Запуск: python quality/profile.py
Пише quality/profile_baseline.md і quality/metrics.json.
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality.common import AS_OF, edges_by_start, load_rdf, operations, read_csv

THRESHOLDS = {
    "completeness_noncash_counterparty": 0.95,
    "consistency_budget": 1.0,
    "consistency_report": 1.0,
    "accuracy_expert": 0.9,
    "timeliness": 1.0,
    "uniqueness_name": 1.0,
    "provenance_csv": 0.95,
    "validity": 1.0,
}


def keyword_category(description):
    text = description.casefold()
    rules = [
        ("оренд", "Cat_Rent"),
        ("продукт", "Cat_Food"),
        ("харч", "Cat_Food"),
        ("таксі", "Cat_Transport"),
        ("транспорт", "Cat_Transport"),
        ("зарплат", "Cat_Salary"),
        ("фриланс", "Cat_Freelance"),
        ("комунал", "Cat_Utilities"),
        ("зв'язок", "Cat_Telecom"),
        ("інтернет", "Cat_Telecom"),
        ("відсот", "Cat_Interest"),
        ("накопич", "Cat_SavingsTransfer"),
    ]
    for stem, category in rules:
        if stem in text:
            return category
    return None


def expert_sample(ops, edges):
    usd = [row for row in ops if row["currency"] == "USD"]
    rest = [row for row in ops if row["currency"] != "USD"]
    random.seed(42)
    chosen = usd + random.sample(rest, 30 - len(usd))
    rows = []
    for row in chosen:
        category = next((edge["end"] for edge in edges[row["id"]] if edge["type"] == "IN_CATEGORY"), "")
        expected = keyword_category(row["description"])
        problems = []
        if float(row["amount"]) <= 0:
            problems.append("сума не додатна")
        datetime.strptime(row["date"], "%Y-%m-%d")
        if expected and category and category != expected:
            problems.append(f"категорія {category}, а опис веде на {expected}")
        if row["currency"] == "USD" and "USD" not in row["description"]:
            problems.append("валюта USD не видна з опису")
        rows.append(
            {
                "id": row["id"],
                "date": row["date"],
                "amount": row["amount"],
                "currency": row["currency"],
                "description": row["description"],
                "category": category,
                "expert": "fail" if problems else "ok",
                "note": "; ".join(problems),
            }
        )
    return rows


def budget_consistency():
    ok = 0
    total = 0
    for row in read_csv("budgets.csv"):
        total += 1
        expected = float(row["actual"]) - float(row["planned"])
        if abs(expected - float(row["deviation"])) < 0.01:
            ok += 1
    return ok / total, total


def report_consistency(graph):
    query = """
    PREFIX fin: <http://example.org/financial-operations#>
    SELECT ?report ?total ?sum WHERE {
      ?report a fin:CashFlowReport ; fin:totalExpenses ?total .
      { SELECT ?report (SUM(?amount) AS ?sum) WHERE {
          ?report fin:aggregates ?op .
          ?op a fin:Expense ; fin:amount ?amount .
        } GROUP BY ?report }
    }
    """
    rows = list(graph.query(query))
    if not rows:
        return 0.0, 0
    ok = sum(1 for _report, total, summed in rows if abs(float(total) - float(summed)) < 0.01)
    return ok / len(rows), len(rows)


def validity():
    accounts = read_csv("accounts.csv")
    parties = read_csv("counterparties.csv")
    ops = operations()
    checks = []
    checks.extend(row["accountNumber"].startswith("UA") and row["accountNumber"][2:].isdigit() for row in accounts)
    checks.extend(len(row["edrpou"]) == 8 and row["edrpou"].isdigit() for row in parties)
    checks.extend(float(row["amount"]) > 0 for row in ops)
    return sum(checks) / len(checks), len(checks)


def provenance(edges):
    ops = operations()
    have = 0
    for row in ops:
        if any(edge["type"] == "DERIVED_FROM" for edge in edges[row["id"]]):
            have += 1
    return have / len(ops), len(ops)


def counterparty_fill(edges):
    missing = []
    considered = []
    for row in operations():
        if row["kind"] != "Expense":
            continue
        if "готівка" in row["description"]:
            continue
        considered.append(row)
        linked = any(edge["type"] == "WITH_COUNTERPARTY" for edge in edges[row["id"]])
        if not linked:
            missing.append(row)
    ratio = (len(considered) - len(missing)) / len(considered)
    return ratio, missing


def uniqueness():
    names = [row["name"].casefold() for row in read_csv("counterparties.csv")]
    return len(set(names)) / len(names), len(names) - len(set(names))


def timeliness():
    today = datetime.strptime(AS_OF, "%Y-%m-%d").date()
    bad = 0
    for row in operations():
        stamp = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if stamp > today:
            bad += 1
    total = len(operations())
    return (total - bad) / total, bad


def rdf_provenance(graph):
    query = """
    PREFIX fin: <http://example.org/financial-operations#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT (COUNT(?op) AS ?ops) (SUM(IF(BOUND(?src), 1, 0)) AS ?with) WHERE {
      ?op a fin:FinancialOperation .
      OPTIONAL { ?op prov:wasDerivedFrom ?src }
    }
    """
    # FinancialOperation may be a superclass not used as a direct type.
    query = """
    PREFIX fin: <http://example.org/financial-operations#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT ?op ?src WHERE {
      VALUES ?kind { fin:Expense fin:Income }
      ?op a ?kind .
      OPTIONAL { ?op prov:wasDerivedFrom ?src }
    }
    """
    rows = list(graph.query(query))
    if not rows:
        return 0.0, 0
    with_source = sum(1 for _op, src in rows if src is not None)
    return with_source / len(rows), len(rows)


def metric(name, dimension, value, threshold, detail):
    return {
        "name": name,
        "dimension": dimension,
        "value": round(value, 4),
        "threshold": threshold,
        "passed": value >= threshold,
        "detail": detail,
    }


def write_markdown(metrics, missing, sample):
    failed = [item for item in metrics if not item["passed"]]
    lines = [
        "# Профіль якості, baseline",
        "",
        f"Версія сховища: CSV ЛР9 і `8/data.ttl` станом на {AS_OF}. Це baseline-1, дату зафіксовано в `quality/metrics.json`.",
        "",
        "Готівкові витрати свідомо не входять у повноту контрагента: в описі немає сторони, і вимагати її було б вигадкою.",
        "",
        "| Метрика | Вимір | Значення | Поріг | |",
        "|---|---|---:|---:|---|",
    ]
    for item in metrics:
        mark = "проходить" if item["passed"] else "нижче порога"
        lines.append(
            f"| {item['name']} | {item['dimension']} | {item['value']:.3f} | {item['threshold']:.2f} | {mark} |"
        )
    lines += ["", "## Що не пройшло", ""]
    if missing:
        lines.append(
            "Без контрагента лишились не-готівкові витрати: "
            + ", ".join(f"{row['id']} ({row['description']}, {row['date']})" for row in missing)
            + "."
        )
        lines.append("")
    for item in failed:
        lines.append(f"- {item['name']}: {item['detail']}")
    lines += [
        "",
        "## Експертна вибірка",
        "",
        f"30 записів: усі {sum(1 for row in sample if row['currency']=='USD')} операцій в USD і решта випадкових витрат чи доходів (seed 42). "
        f"Помилок за карткою перевірки: {sum(1 for row in sample if row['expert']=='fail')}. Картка — `quality/accuracy_sample.csv`.",
        "",
        "## Три пріоритети для RAG",
        "",
        "1. Повнота контрагента на безготівкових витратах. Питання «кому сплачено за транспорт чи харчування у вересні» в графі не має ребра, хоча операція є. Для RAG це пропуск контексту, не привід вигадувати магазин.",
        "2. Походження в RDF-зрізі ЛР8. У CSV є DERIVED_FROM, у Turtle операції такого ребра немає. Відповідь з графа ЛР8 не може показати джерело.",
        "3. Формулювання ризику «частка оренди понад 70% усіх витрат». На повному ряді витрат частка нижча, понад 70% вона лише в окремі місяці. RAG, який процитує опис ризику дослівно, дасть зашироке твердження.",
        "",
    ]
    (ROOT / "quality" / "profile_baseline.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    edges = edges_by_start()
    ops = operations()
    graph = load_rdf()
    fill, missing = counterparty_fill(edges)
    budget, budget_n = budget_consistency()
    reports, report_n = report_consistency(graph)
    sample = expert_sample(ops, edges)
    accuracy = sum(1 for row in sample if row["expert"] == "ok") / len(sample)
    dated, future = timeliness()
    unique, dup_names = uniqueness()
    prov, prov_n = provenance(edges)
    valid, valid_n = validity()
    rdf_prov, rdf_n = rdf_provenance(graph)
    accessible = 1.0 if report_n else 0.0
    metrics = [
        metric("частка безготівкових витрат із контрагентом", "повнота", fill, THRESHOLDS["completeness_noncash_counterparty"], f"без ребра: {len(missing)}"),
        metric("deviation = actual − planned", "узгодженість", budget, THRESHOLDS["consistency_budget"], f"бюджетів {budget_n}"),
        metric("звіт дорівнює сумі своїх витрат", "узгодженість", reports, THRESHOLDS["consistency_report"], f"звітів {report_n}"),
        metric("експертна вибірка 30 записів", "точність", accuracy, THRESHOLDS["accuracy_expert"], "картка accuracy_sample.csv"),
        metric("дата є і не пізніше 2026-11-03", "актуальність", dated, THRESHOLDS["timeliness"], f"дат у майбутньому: {future}"),
        metric("унікальність точної назви контрагента", "унікальність", unique, THRESHOLDS["uniqueness_name"], f"повторень назви: {dup_names}"),
        metric("DERIVED_FROM у CSV-графі", "походження", prov, THRESHOLDS["provenance_csv"], f"операцій {prov_n}"),
        metric("prov:wasDerivedFrom у RDF", "походження", rdf_prov, 0.9, f"операцій RDF {rdf_n}"),
        metric("рахунки, ЄДРПОУ, додатні суми", "валідність", valid, THRESHOLDS["validity"], f"перевірок {valid_n}"),
        metric("Turtle читається і SPARQL повертає звіти", "доступність", accessible, 1.0, "data.ttl"),
    ]
    payload = {"version": "baseline-1", "date": AS_OF, "metrics": metrics}
    (ROOT / "quality" / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    import csv

    with (ROOT / "quality" / "accuracy_sample.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sample[0]))
        writer.writeheader()
        writer.writerows(sample)
    write_markdown(metrics, missing, sample)
    for item in metrics:
        print(f"{item['value']:.3f} {'OK' if item['passed'] else 'LOW'} {item['name']}")


if __name__ == "__main__":
    main()
