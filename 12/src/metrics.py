import json
from pathlib import Path

import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
SPEC = ROOT / "semantic" / "metrics.yml"

BASE = {
    "total_expense": "SELECT round(sum(amount), 2) AS value FROM v_operation WHERE kind = 'Expense'{extra}",
    "total_income": "SELECT round(sum(amount), 2) AS value FROM v_operation WHERE kind = 'Income'{extra}",
    "net_cashflow": """SELECT round(sum(CASE WHEN kind = 'Income' THEN amount
        WHEN kind = 'Expense' THEN -amount ELSE 0 END), 2) AS value
        FROM v_operation WHERE 1 = 1{extra}""",
    "avg_expense": "SELECT round(avg(amount), 2) AS value FROM v_operation WHERE kind = 'Expense'{extra}",
    "expense_share": """SELECT round(sum(CASE WHEN category_id = '{category_id}' THEN amount END)
        / sum(amount), 4) AS value
        FROM v_operation WHERE kind = 'Expense'{extra}""",
    "budget_usage": """SELECT round(sum(amount) / max(budget_limit_uah), 4) AS value
        FROM v_operation WHERE kind = 'Expense'{extra}""",
}


def load_spec():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def sql_for(name, **filters):
    if name not in BASE:
        raise KeyError(name)
    if name == "expense_share" and "category_id" not in filters:
        raise ValueError("expense_share потребує category_id")
    if name == "budget_usage" and not {"category_id", "month_key"} <= set(filters):
        raise ValueError("budget_usage потребує category_id і month_key")
    extra_filters = dict(filters)
    category = extra_filters.pop("category_id", None) if name == "expense_share" else filters.get("category_id")
    parts = []
    for key, value in filters.items():
        if name == "expense_share" and key == "category_id":
            continue
        if isinstance(value, str):
            parts.append(f"{key} = '{value}'")
        else:
            parts.append(f"{key} = {int(value)}")
    extra = (" AND " + " AND ".join(parts)) if parts else ""
    sql = BASE[name].format(extra=extra, category_id=category or "")
    return " ".join(sql.split())


def run(con, sql):
    return con.execute(sql).fetchone()[0]


def pandas_total_expense(year):
    fact = pd.read_parquet(ROOT / "data" / "fact_operation.parquet")
    dates = pd.read_parquet(ROOT / "data" / "dim_date.parquet")
    rows = fact.merge(dates, on="date_sk")
    return round(float(rows[(rows.kind == "Expense") & (rows.year == year)].amount.sum()), 2)


def main():
    spec = load_spec()
    names = [m["name"] for m in spec["metrics"]]
    required = {"name", "definition", "formula", "unit", "owner", "sources", "limitations", "status", "reviewed_on"}
    missing = [m["name"] for m in spec["metrics"] if not required <= set(m)]
    con = duckdb.connect(str(DB), read_only=True)
    direct = "SELECT round(sum(amount), 2) FROM v_operation WHERE kind = 'Expense' AND year = 2026"
    via_metric = sql_for("total_expense", year=2026)
    pandas_value = pandas_total_expense(2026)
    a, b = run(con, via_metric), run(con, direct)
    share_sql = sql_for("expense_share", year=2026, category_id="Cat_Rent")
    share_direct = """
        SELECT round(sum(CASE WHEN category_id = 'Cat_Rent' THEN amount END) / sum(amount), 4)
        FROM v_operation WHERE kind = 'Expense' AND year = 2026
    """
    checks = [
        {"name": "fields", "ok": not missing, "detail": missing or "усі поля є"},
        {"name": "total_expense_2026", "metric": a, "direct_sql": b, "pandas": pandas_value,
         "ok": a == b == pandas_value},
        {"name": "expense_share_rent_2026", "metric": run(con, share_sql), "direct_sql": run(con, share_direct),
         "ok": run(con, share_sql) == run(con, share_direct)},
    ]
    lines = ["# Семантичний шар", "",
             f"Файл `semantic/metrics.yml`, переглянуто {spec['reviewed_on']}, власник — {spec['owner']}.",
             "Функція `sql_for` у `src/metrics.py` будує SQL за назвою метрики.", "",
             "| Метрика | Одиниця | Формула | Обмеження | Статус |",
             "|---|---|---|---|---|"]
    for m in spec["metrics"]:
        lines.append(f"| {m['name']} | {m['unit']} | {m['formula']} | {m['limitations']} | {m['status']} |")
    lines += ["", "## Узгодженість двох шляхів", ""]
    for c in checks:
        lines.append(f"- {c['name']}: {json.dumps(c, ensure_ascii=False)}")
    lines.append("")
    (ROOT / "docs" / "semantic_layer.md").write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "docs" / "semantic_raw.json").write_text(
        json.dumps({"metrics": names, "checks": checks, "sql": {"total_expense": via_metric, "share": share_sql}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(c["ok"] for c in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
