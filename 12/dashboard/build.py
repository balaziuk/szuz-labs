from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=120)
    plt.close()


def main():
    con = duckdb.connect(str(DB), read_only=True)
    monthly = con.execute("""
        SELECT month_key,
               sum(CASE WHEN kind = 'Income' THEN amount ELSE 0 END) AS income,
               sum(CASE WHEN kind = 'Expense' THEN amount ELSE 0 END) AS expense
        FROM v_operation WHERE year = 2026
        GROUP BY month_key ORDER BY month_key
    """).fetchdf()
    by_cat = con.execute("""
        SELECT category_name, sum(amount) AS expense
        FROM v_operation WHERE kind = 'Expense' AND year = 2026
        GROUP BY 1 ORDER BY expense DESC
    """).fetchdf()
    tops = con.execute("""
        SELECT counterparty_name, sum(amount) AS expense
        FROM v_operation
        WHERE kind = 'Expense' AND year = 2026 AND counterparty_id <> 'Cp_Cash'
        GROUP BY 1 ORDER BY expense DESC LIMIT 5
    """).fetchdf()
    food = con.execute("""
        SELECT month_key, sum(amount) AS food,
               avg(sum(amount)) OVER (ORDER BY month_key ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS ma3
        FROM v_operation
        WHERE kind = 'Expense' AND year = 2026 AND category_id = 'Cat_Food'
        GROUP BY month_key ORDER BY month_key
    """).fetchdf()

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(monthly.month_key, monthly.income, marker="o", label="доходи")
    ax.plot(monthly.month_key, monthly.expense, marker="o", label="витрати")
    ax.set_title("Доходи і витрати по місяцях, 2026")
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    ax.set_ylabel("грн")
    save(fig, "01_income_expense.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(by_cat.category_name[::-1], by_cat.expense[::-1])
    ax.set_title("Витрати за категоріями, 2026")
    ax.set_xlabel("грн")
    save(fig, "02_by_category.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(tops.counterparty_name[::-1], tops.expense[::-1])
    ax.set_title("П'ять контрагентів із найбільшими витратами, 2026")
    ax.set_xlabel("грн")
    save(fig, "03_counterparties.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(food.month_key, food.food, marker="o", label="харчування")
    ax.plot(food.month_key, food.ma3, marker="o", label="ковзне середнє 3 міс.")
    ax.set_title("Харчування і ковзне середнє, 2026")
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    ax.set_ylabel("грн")
    save(fig, "04_food_ma.png")

    last_net = con.execute("""
        SELECT round(sum(CASE WHEN kind = 'Income' THEN amount WHEN kind = 'Expense' THEN -amount ELSE 0 END), 2)
        FROM v_operation WHERE year = 2026
    """).fetchone()[0]
    notes = f"""# Інтерпретації панелі

Питання ті самі, що в OLAP і семантичному шарі. Усі суми — гривні, 2026 рік (січень–жовтень).

1. `01_income_expense.png`. Доходи щомісяця тримаються біля зарплати й фрилансу, витрати — біля оренди, комунальних і покупок. Різниця між лініями — місячний чистий потік.
2. `02_by_category.png`. Найвищий стовпець — оренда: 15 000 грн кожного місяця, тобто 150 000 грн за 10 місяців 2026. Далі йдуть харчування і комунальні.
3. `03_counterparties.png`. Найбільший контрагент витрат — орендодавець, бо оренда фіксована і більша за разові покупки. Готівку без контрагента в рейтинг не включено.
4. `04_food_ma.png`. Місячні витрати на харчування стрибають, бо кількість покупок випадкова (seed 42). Ковзне середнє згладжує ці стрибки.

Чистий потік за 2026 (доходи мінус витрати): {last_net} грн.
"""
    (OUT / "interpretations.md").write_text(notes, encoding="utf-8")
    print("charts ok", last_net)


if __name__ == "__main__":
    main()
