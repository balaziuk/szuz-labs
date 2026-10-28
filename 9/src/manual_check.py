import csv
import json
from collections import defaultdict

from run_cypher import ROOT

DATA = ROOT / "data"


def rows(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


ops = {r["id"]: r for r in rows("operations.csv")}
cats = {r["id"]: r for r in rows("categories.csv")}
cps = {r["id"]: r for r in rows("counterparties.csv")}
rels = rows("relationships.csv")
cat_of = {r["start"]: r["end"] for r in rels if r["type"] == "IN_CATEGORY"}
cp_of = {r["start"]: r["end"] for r in rels if r["type"] == "WITH_COUNTERPARTY"}
acc_of = {r["start"]: r["end"] for r in rels if r["type"] == "FROM_ACCOUNT"}

raw = json.loads((ROOT / "docs" / "cypher_raw.json").read_text(encoding="utf-8"))
report = ["# Р3. Ручна перевірка запитів на підграфі (CSV → Python)\n"]

exp = [(o["id"], float(o["amount"]), o["date"], cats[cat_of[o["id"]]]["name"])
       for o in ops.values() if o["kind"] == "Expense" and o["date"].startswith("2026-09")]
exp.sort(key=lambda x: x[2])
neo = [(r["operation"], r["amount"], r["date"], r["category"]) for r in raw["Q01_expenses_sep"]["rows"]]
report.append("## Q01 — витрати вересня 2026\n")
report.append("Підграф: 4 операції вересня в operations.csv, з них 3 мають kind=Expense.\n")
report.append("| Операція | Сума | Дата | Категорія |\n|---|---|---|---|")
report += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in exp]
report.append(f"\nСума вручну: {sum(x[1] for x in exp)}; Neo4j: {sum(x[1] for x in neo)}. "
              f"Збіг рядків: **{exp == neo}**.\n")

total = sum(float(o["amount"]) for o in ops.values() if o["kind"] == "Expense")
by_cp = defaultdict(lambda: [0, 0.0])
for o in ops.values():
    if o["kind"] == "Expense" and o["id"] in cp_of:
        by_cp[cp_of[o["id"]]][0] += 1
        by_cp[cp_of[o["id"]]][1] += float(o["amount"])
top = sorted(by_cp.items(), key=lambda kv: -kv[1][1])[:5]
mine = [(cps[k]["name"], n, s, round(100 * s / total, 2)) for k, (n, s) in top]
neo = [(r["counterparty"], r["operations"], r["total"], r["percentOfExpenses"])
       for r in raw["Q04_top_counterparties"]["rows"]]
report.append("## Q04 — топ-5 контрагентів за витратами\n")
report.append(f"Усього витрат (вручну): {total}.\n")
report.append("| Контрагент | Операцій | Сума | % |\n|---|---|---|---|")
report += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in mine]
report.append(f"\nЗбіг з Neo4j: **{mine == neo}**.\n")

by_m = defaultdict(lambda: {"Income": 0.0, "Expense": 0.0, "Transfer": 0.0})
for o in ops.values():
    if acc_of[o["id"]] == "Acc_UA123456789":
        by_m[o["date"][:7]][o["kind"]] += float(o["amount"])
mine = [(m, v["Income"], v["Expense"], v["Transfer"], v["Income"] - v["Expense"] - v["Transfer"])
        for m, v in sorted(by_m.items())]
neo = [(r["month"], r["income"], r["expenses"], float(r["toSavings"]), r["net"])
       for r in raw["Q06_monthly_balance"]["rows"]]
report.append("## Q06 — доходи, витрати й сальдо по місяцях\n")
report.append("| Місяць | Доходи | Витрати | На накопичення | Сальдо |\n|---|---|---|---|---|")
report += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in mine]
report.append(f"\nЗбіг з Neo4j: **{mine == neo}**.\n")

(ROOT / "docs" / "manual_check.md").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))
