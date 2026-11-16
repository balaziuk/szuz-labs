"""Локальний gate. Код виходу 1, якщо сховище або навмисний дефект не спійманий.

Перевірки чотирьох типів: SHACL (pyshacl, quality/shapes.ttl), SPARQL-інваріанти,
JSON Schema, pytest-правила. `python quality/gate.py --inject amount|account|budget`
вносить дефект у копію реального сховища й має завершитися кодом 1 — так CI ловить дефект.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator, FormatChecker
from pyshacl import validate as shacl_validate
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, XSD

from quality.common import AS_OF, load_rdf, operations, read_csv

FIN = Namespace("http://example.org/financial-operations#")


SHAPES = ROOT / "quality" / "shapes.ttl"
SH = Namespace("http://www.w3.org/ns/shacl#")


def shacl_check(graph):
    """Справжня SHACL-валідація (pyshacl) за quality/shapes.ttl."""
    conforms, report, _text = shacl_validate(graph, shacl_graph=str(SHAPES), inference="none")
    if conforms:
        return []
    errors = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        path = report.value(result, SH.resultPath)
        focus = report.value(result, SH.focusNode)
        message = report.value(result, SH.resultMessage)
        errors.append(f"SHACL {str(path).rsplit('#', 1)[-1]} {focus}: {message}")
    return sorted(set(errors))


# Стара назва лишається для тестів.
shacl_like = shacl_check


def sparql_invariants(graph):
    errors = []
    deviation = """
    PREFIX fin: <http://example.org/financial-operations#>
    SELECT ?b ?planned ?actual ?dev WHERE {
      ?b a fin:Budget ; fin:plannedAmount ?planned ; fin:actualAmount ?actual ; fin:deviation ?dev .
    }
    """
    for _b, planned, actual, dev in graph.query(deviation):
        if abs((float(actual) - float(planned)) - float(dev)) > 0.01:
            errors.append("SPARQL budget deviation")
    summed = {}
    declared = {}
    for report, total, amount in graph.query(
        """
        PREFIX fin: <http://example.org/financial-operations#>
        SELECT ?report ?total ?amount WHERE {
          ?report a fin:CashFlowReport ; fin:totalExpenses ?total ; fin:aggregates ?op .
          ?op a fin:Expense ; fin:amount ?amount .
        }
        """
    ):
        declared[report] = float(total)
        summed[report] = summed.get(report, 0.0) + float(amount)
    for report, total in declared.items():
        if abs(total - summed[report]) > 0.01:
            errors.append(f"SPARQL report sum {report}")
    income_expense = """
    PREFIX fin: <http://example.org/financial-operations#>
    SELECT ?op WHERE { ?op a fin:Income, fin:Expense . }
    """
    if list(graph.query(income_expense)):
        errors.append("SPARQL income and expense")
    return errors


def schema_errors(rows):
    schema = json.loads((ROOT / "quality" / "operation.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for row in rows:
        payload = {
            "id": row["id"],
            "kind": row["kind"],
            "amount": float(row["amount"]),
            "date": row["date"],
            "currency": row["currency"],
            "description": row["description"],
        }
        errors.extend(f"JSON {row['id']} {error.message}" for error in validator.iter_errors(payload))
    return errors


def pytest_rules():
    errors = []
    ids = [row["id"] for row in operations()]
    if len(ids) != len(set(ids)):
        errors.append("pytest duplicate operation id")
    codes = [row["edrpou"] for row in read_csv("counterparties.csv")]
    if any(len(code) != 8 for code in codes):
        errors.append("pytest edrpou length")
    if AS_OF != "2026-11-03":
        errors.append("pytest as-of")
    return errors


def run_suite(graph, rows):
    found = []
    found.extend(shacl_check(graph))
    found.extend(sparql_invariants(graph))
    found.extend(schema_errors(rows))
    found.extend(pytest_rules())
    return found


def defect_graph(kind):
    graph = Graph()
    graph.bind("fin", FIN)
    if kind == "amount":
        node = FIN.BadAmount
        graph.add((node, RDF.type, FIN.Expense))
        graph.add((node, FIN.amount, Literal(-5, datatype=XSD.decimal)))
        graph.add((node, FIN.belongsToAccount, FIN.Acc_UA123456789))
        graph.add((node, FIN.belongsToCategory, FIN.Cat_Food))
    elif kind == "account":
        node = FIN.BadAccount
        graph.add((node, RDF.type, FIN.CurrentAccount))
        graph.add((node, FIN.accountNumber, Literal("123")))
    elif kind == "budget":
        node = FIN.BadBudget
        graph.add((node, RDF.type, FIN.Budget))
        graph.add((node, FIN.plannedAmount, Literal(10)))
        graph.add((node, FIN.actualAmount, Literal(30)))
        graph.add((node, FIN.deviation, Literal(0)))
    return graph


CHECKS = [
    ("SHACL", "сума витрати додатна, decimal", "amount"),
    ("SHACL", "витрата має рахунок", "belongsToAccount"),
    ("SHACL", "витрата має категорію", "belongsToCategory"),
    ("SHACL", "номер рахунку ^UA[0-9]+$", "accountNumber"),
    ("SHACL", "ЄДРПОУ — 8 цифр", "edrpouCode"),
    ("SPARQL", "deviation = actual − planned", "budget deviation"),
    ("SPARQL", "звіт = сума своїх витрат", "report sum"),
    ("SPARQL", "операція не є водночас доходом і витратою", "income and expense"),
    ("JSON Schema", "id ^Op_[0-9]{5}$, сума > 0, дата, валюта UAH/USD", "JSON"),
    ("pytest", "унікальні id операцій", "duplicate operation id"),
    ("pytest", "ЄДРПОУ у CSV — 8 символів", "edrpou length"),
    ("pytest", "дата зрізу зафіксована", "as-of"),
]


def count_by_check(violations):
    return [sum(1 for item in violations if marker in item) for _tool, _rule, marker in CHECKS]


def inject(kind):
    graph = load_rdf()
    for triple in defect_graph(kind):
        graph.add(triple)
    return graph


def main():
    import csv
    from datetime import datetime, timezone

    if len(sys.argv) > 2 and sys.argv[1] == "--inject":
        violations = run_suite(inject(sys.argv[2]), operations())
        for item in violations:
            print(item)
        print(f"gate: порушень {len(violations)}")
        raise SystemExit(1 if violations else 0)

    clean = run_suite(load_rdf(), operations())
    caught = {kind: run_suite(inject(kind), operations()) for kind in ("amount", "account", "budget")}
    bad_row = [{"id": "Op_1", "kind": "Expense", "amount": "-3", "date": "не-дата", "currency": "EUR", "description": ""}]
    schema_fail = schema_errors(operations() + bad_row)
    columns = {"чисте сховище": clean, **{f"дефект {k}": v for k, v in caught.items()}, "дефект JSON-рядка": schema_fail}
    lines = [
        "# Журнал gate",
        "",
        f"Дата прогону: {datetime.now(timezone.utc).date().isoformat()}. Перевірок: {len(CHECKS)}, інструментів: {len({c[0] for c in CHECKS})}.",
        "",
        "## Порушення за правилами",
        "",
        "| інструмент | правило | " + " | ".join(columns) + " |",
        "| --- | --- | " + " | ".join("---:" for _ in columns) + " |",
    ]
    counts = {name: count_by_check(v) for name, v in columns.items()}
    for index, (tool, rule, _marker) in enumerate(CHECKS):
        lines.append(f"| {tool} | {rule} | " + " | ".join(str(counts[name][index]) for name in columns) + " |")
    lines.append("| **разом** | | " + " | ".join(f"**{len(v)}**" for v in columns.values()) + " |")
    lines += ["", "## Деталі дефектів", ""]
    for name, violations in columns.items():
        if name == "чисте сховище":
            continue
        lines.append(f"{name}:")
        lines.extend(f"- {item}" for item in violations[:6])
        lines.append("")
    trend_path = ROOT / "quality" / "gate_trend.csv"
    new_file = not trend_path.exists()
    with trend_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["time", "clean_violations", "amount", "account", "budget", "json"])
        writer.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), len(clean), *[len(v) for v in caught.values()], len(schema_fail)])
    trend = list(csv.DictReader(trend_path.read_text(encoding="utf-8").splitlines()))
    lines += ["## Тренд (quality/gate_trend.csv)", "", "| прогін | порушень у чистому сховищі |", "| --- | ---: |"]
    lines.extend(f"| {row['time']} | {row['clean_violations']} |" for row in trend[-10:])
    (ROOT / "quality" / "gate_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok = not clean and all(caught.values()) and schema_fail
    print(f"clean={len(clean)} defects={[len(v) for v in caught.values()]} schema={len(schema_fail)}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
