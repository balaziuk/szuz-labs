import json
import sys
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.generate import FIRST, LAST, SEED, build

DATA = ROOT / "data"
DOCS = ROOT / "docs"
DB = DATA / "warehouse.duckdb"
VERSION = "lab12-facts-v1"


def frames(con, tables):
    for name, rows in tables.items():
        con.register(name + "_src", pd.DataFrame(rows))
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_src")


def quality(con):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    n = con.execute("SELECT count(*) FROM fact_operation").fetchone()[0]
    add("fact_rows_at_least_1000", n >= 1000, f"рядків факту: {n}")
    add("amount_not_null_positive",
        con.execute("SELECT count(*) FROM fact_operation WHERE amount IS NULL OR amount <= 0").fetchone()[0] == 0,
        "amount NOT NULL і > 0")
    add("kind_domain",
        con.execute("""SELECT count(*) FROM fact_operation
                       WHERE kind NOT IN ('Income','Expense','Transfer')""").fetchone()[0] == 0,
        "kind лише Income, Expense, Transfer")
    add("operation_id_unique",
        con.execute("""SELECT count(*) FROM (
                         SELECT operation_id FROM fact_operation GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0] == 0,
        "operation_id унікальний")
    for dim, col in (("dim_date", "date_sk"), ("dim_account", "account_sk"), ("dim_category", "category_sk"),
                     ("dim_counterparty", "counterparty_sk"), ("dim_source", "source_sk")):
        orphans = con.execute(f"""
            SELECT count(*) FROM fact_operation f
            LEFT JOIN {dim} d ON f.{col} = d.{col}
            WHERE d.{col} IS NULL""").fetchone()[0]
        add(f"no_orphan_{col}", orphans == 0, f"сиріт за {col}: {orphans}")
    bad_iri = con.execute("""
        SELECT count(*) FROM dim_category
        WHERE iri IS NULL OR iri NOT LIKE 'http://example.org/financial-operations#%'
    """).fetchone()[0]
    add("category_iri", bad_iri == 0, f"категорій без IRI таксономії: {bad_iri}")
    span = con.execute("SELECT min(full_date), max(full_date) FROM dim_date").fetchone()
    add("date_span", str(span[0]) == str(FIRST) and str(span[1]) == str(LAST),
        f"календар {span[0]} … {span[1]}")
    return checks


def star_diagram(path):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    fact = (3.7, 2.2, 2.6, 1.6, "fact_operation\nзерно: 1 операція\nFK date_sk, account_sk, category_sk,\n"
            "counterparty_sk, source_sk\namount (адитивна)")
    dims = [
        (0.2, 4.6, "dim_date\nрік → квартал → місяць"),
        (3.7, 4.6, "dim_account\nтип рахунку, snapshot_balance"),
        (7.2, 4.6, "dim_category\nстаття → група → клас, IRI"),
        (0.2, 0.3, "dim_counterparty\nSCD тип 2"),
        (7.2, 0.3, "dim_source\nбанк / готівка"),
    ]
    fx, fy, fw, fh, ftext = fact
    for x, y, _ in dims:
        top = y > fy
        ax.plot([x + 1.3, min(max(x + 1.3, fx + 0.3), fx + fw - 0.3)], [y if top else y + 1.0, fy + fh if top else fy],
                color="#555", linewidth=1, zorder=1)
    for x, y, w, h, text, color in [(fx, fy, fw, fh, ftext, "#f4e4c4")] + [(x, y, 2.6, 1.0, t, "#e7eef6") for x, y, t in dims]:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", facecolor=color, edgecolor="#333", zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8, zorder=3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close()


def write_quality_md(checks, n):
    lines = ["# Перевірки якості завантаження", "",
             f"Версія даних: `{VERSION}`. Генератор: `etl/generate.py`, seed {SEED}.",
             f"Факт: {n} рядків. Parquet: `data/*.parquet`.", "",
             "| Перевірка | Результат | Деталь |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['name']} | {'так' if c['ok'] else 'ні'} | {c['detail']} |")
    failed = [c["name"] for c in checks if not c["ok"]]
    lines += ["", f"Провалено: {', '.join(failed) if failed else 'немає'}.", ""]
    (DOCS / "quality_checks.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    DATA.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    tables = build()
    meta = {k: tables.pop(k) for k in ("seed", "n_facts")}
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    frames(con, tables)
    con.execute((ROOT / "sql" / "views.sql").read_text(encoding="utf-8"))
    for name in tables:
        dest = str(DATA / f"{name}.parquet").replace("\\", "/")
        con.execute(f"COPY {name} TO '{dest}' (FORMAT PARQUET)")
    checks = quality(con)
    n = meta["n_facts"]
    (DATA / "VERSION").write_text(
        f"{VERSION}\nseed={meta['seed']}\ngenerator=etl/generate.py\nrows={n}\n", encoding="utf-8")
    (DOCS / "quality_raw.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    write_quality_md(checks, n)
    star_diagram(DOCS / "star.png")
    print("facts", n)
    for c in checks:
        print(("OK " if c["ok"] else "FAIL"), c["name"], c["detail"])
    if not all(c["ok"] for c in checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
