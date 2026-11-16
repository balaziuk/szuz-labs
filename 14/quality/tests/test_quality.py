import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quality.common import read_csv
from quality.dedup import attribute_score, string_score
from quality.gate import defect_graph, schema_errors, shacl_like, sparql_invariants


def test_budget_deviation_matches_actual_minus_planned():
    for row in read_csv("budgets.csv"):
        assert abs(float(row["actual"]) - float(row["planned"]) - float(row["deviation"])) < 0.01


def test_operation_ids_unique():
    ids = [row["id"] for row in read_csv("operations.csv")]
    assert len(ids) == len(set(ids))


def test_edrpou_is_eight_digits():
    for row in read_csv("counterparties.csv"):
        assert row["edrpou"].isdigit() and len(row["edrpou"]) == 8


def test_privat_alias_is_closer_than_unrelated_name():
    assert string_score("Приват", "ПриватБанк") > string_score("Приват", "Сільпо")


def test_different_edrpou_scores_zero():
    assert attribute_score("14360570", "21673832") == 0


def test_negative_amount_fails_shacl():
    assert shacl_like(defect_graph("amount"))


def test_bad_budget_fails_sparql():
    assert sparql_invariants(defect_graph("budget"))


def test_json_schema_rejects_broken_operation():
    row = [{"id": "Op_1", "kind": "Expense", "amount": "-3", "date": "не-дата", "currency": "EUR", "description": ""}]
    assert schema_errors(row)


def test_shapes_file_mentions_ten_constraints_across_tools():
    shapes = (ROOT / "quality" / "shapes.ttl").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "quality" / "operation.schema.json").read_text(encoding="utf-8"))
    assert "sh:minCount" in shapes and "sh:pattern" in shapes
    assert "exclusiveMinimum" in schema["properties"]["amount"]
