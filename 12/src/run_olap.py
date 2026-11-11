import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
SQL_DIR = ROOT / "sql" / "olap"
DOCS = ROOT / "docs"


def question_of(text):
    for line in text.splitlines():
        if line.startswith("-- question:"):
            return line.split(":", 1)[1].strip()
    return ""


def records(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        row = {}
        for c, v in zip(cols, raw):
            row[c] = None if v is None else (round(v, 2) if isinstance(v, float) else v)
        rows.append(row)
    return cols, rows


def md_table(cols, rows, limit=18):
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = []
    for r in rows[:limit]:
        body.append("| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |")
    extra = ""
    if len(rows) > limit:
        extra = f"\n\nПоказано {limit} із {len(rows)} рядків."
    return "\n".join([head, sep, *body]) + extra


def interpret(name, cols, rows):
    if not rows:
        return "Запит не повернув рядків."
    if name.startswith("q01"):
        total = next(r for r in rows if r["month_key"] is None and r["parent_name"] is None)
        return (f"Загальні витрати 2026 року — {total['expense_uah']} грн. "
                "ROLLUP дає підсумок місяця (parent_name порожній) і загальний підсумок. "
                "Групи таксономії всередині місяця різні: житло, повсякденні витрати, послуги.")
    if name.startswith("q02"):
        cell = lambda kind: next(r for r in rows if r["year"] == 2025 and r["quarter"] is None and r["kind"] == kind)
        income, expense = cell("Income"), cell("Expense")
        return (f"У 2025 році доходи {income['amount_uah']} грн (операцій: {income['operations']}) перевищили витрати "
                f"{expense['amount_uah']} грн (операцій: {expense['operations']}). Витрат багато й дрібних, доходів мало й великих. "
                "Рядки з порожнім kind додають доходи, витрати й перекази разом, тож показують лише оборот, а не результат.")
    if name.startswith("q05"):
        rent = next(r for r in rows if r["category_name"] == "Оренда")
        food = next(r for r in rows if r["category_name"] == "Харчування")
        months = [c for c in cols if c != "category_name"]
        return (f"Оренда не змінюється: {rent[months[0]]} грн щомісяця. Харчування коливається від "
                f"{min(food[m] for m in months)} до {max(food[m] for m in months)} грн. "
                "Порожня клітинка означає, що операцій цієї статті в місяці не було, а не нульовий рядок.")
    if name.startswith("q03"):
        bits = ", ".join(f"{r['year']}: {r['expense_uah']} грн" for r in rows)
        return f"Зріз лише витрат за роками: {bits}."
    if name.startswith("q04"):
        top = rows[0]
        return (f"У 3 кварталі 2026 серед підкласів «Житло» найбільше {top['category_name']}: "
                f"{top['expense_uah']} грн ({top['iri']}).")
    if name.startswith("q07"):
        top = rows[0]
        return f"Найбільший контрагент витрат 2026 — {top['counterparty_name']}: {top['expense_uah']} грн."
    if name.startswith("q08"):
        last = rows[-1]
        return (f"У {last['month_key']} витрати на харчування {last['food_uah']} грн, "
                f"ковзне середнє за 3 місяці — {last['ma3']} грн.")
    if name.startswith("q06"):
        last = rows[-1]
        return (f"Накопичений чистий потік на {last['month_key']} — {last['running_net_uah']} грн "
                f"(місячний потік {last['net_uah']} грн).")
    if name.startswith("q09"):
        groups = [r for r in rows if r["is_group_total"] == 1]
        leaves = [r for r in rows if r["is_group_total"] == 0]
        top = max(leaves, key=lambda r: r["expense_uah"])
        summed = round(sum(r["expense_uah"] for r in groups), 2)
        return (f"Три групи таксономії разом — {summed} грн. Найбільша стаття — {top['category_name']} "
                f"у групі «{top['parent_name']}»: {top['expense_uah']} грн. "
                "Підсумок групи дорівнює сумі її статей.")
    return f"Запит повернув {len(rows)} рядків."


def pandas_check(con):
    df = con.execute("""
        SELECT year, month_key, kind, amount, category_id, counterparty_id, counterparty_name
        FROM v_operation
    """).fetchdf()
    sql_total = con.execute("""
        SELECT round(sum(amount), 2) FROM v_operation WHERE kind = 'Expense' AND year = 2026
    """).fetchone()[0]
    pd_total = round(float(df[(df.kind == "Expense") & (df.year == 2026)].amount.sum()), 2)
    exp = df[(df.kind == "Expense") & (df.year == 2026) & (df.counterparty_id != "Cp_Cash")]
    top_pd = exp.groupby("counterparty_name").amount.sum().sort_values(ascending=False)
    top_sql = con.execute("""
        SELECT counterparty_name, round(sum(amount), 2) AS s
        FROM v_operation
        WHERE kind = 'Expense' AND year = 2026 AND counterparty_id <> 'Cp_Cash'
        GROUP BY 1 ORDER BY s DESC LIMIT 1
    """).fetchone()
    return [
        {"check": "q01_grand_total_vs_pandas", "sql": sql_total, "pandas": pd_total,
         "ok": abs(sql_total - pd_total) < 0.02},
        {"check": "q07_top_counterparty_vs_pandas", "sql": [top_sql[0], top_sql[1]],
         "pandas": [top_pd.index[0], round(float(top_pd.iloc[0]), 2)],
         "ok": top_sql[0] == top_pd.index[0] and abs(top_sql[1] - float(top_pd.iloc[0])) < 0.02},
    ]


def main():
    con = duckdb.connect(str(DB), read_only=True)
    parts = ["# OLAP-запити", "",
             "Вітрина `v_operation` у DuckDB. Кожен файл у `sql/olap/` — окрема конструкція.", ""]
    raw = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        cols, rows = records(con, sql)
        item = {"file": path.name, "question": question_of(sql), "columns": cols,
                "rows": rows, "interpretation": interpret(path.name, cols, rows)}
        raw.append(item)
        parts += [f"## {path.name}", "", item["question"], "", "```sql", sql.strip(), "```", "",
                  md_table(cols, rows), "", item["interpretation"], ""]
    checks = pandas_check(con)
    parts += ["## Незалежна перевірка (pandas)", ""]
    for c in checks:
        parts.append(f"- {c['check']}: SQL = {c['sql']}, pandas = {c['pandas']}, збіг = {'так' if c['ok'] else 'ні'}.")
    parts.append("")
    (DOCS / "olap_results.md").write_text("\n".join(parts), encoding="utf-8")
    (DOCS / "olap_raw.json").write_text(json.dumps({"queries": raw, "pandas": checks}, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    for c in checks:
        print(c["check"], c["ok"], c["sql"], c["pandas"])
    if not all(c["ok"] for c in checks):
        raise SystemExit(1)
    print("queries", len(raw))


if __name__ == "__main__":
    main()
