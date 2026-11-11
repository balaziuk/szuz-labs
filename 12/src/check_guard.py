import json
import sys
from pathlib import Path

import duckdb
import sqlglot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from t2sql import DB, execute, guard, timeout_works


def outer_limit(sql):
    return int(sqlglot.parse_one(sql, read="duckdb").args["limit"].expression.this)


def main():
    cases = [json.loads(ln) for ln in (ROOT / "tests" / "guard_cases.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    con = duckdb.connect(str(DB), read_only=True)
    results = []
    for c in cases:
        safe_sql, reason = guard(c["sql"])
        ok = reason is not None if c["expect"] == "block" else reason is None and outer_limit(safe_sql) == c["limit"]
        if ok and c["expect"] == "pass":
            execute(con, safe_sql)
        results.append({**c, "reason": reason, "output": safe_sql, "ok": ok})
    writes = []
    for sql in ("DELETE FROM fact_operation", "DROP TABLE fact_operation"):
        try:
            con.execute(sql)
            writes.append({"sql": sql, "refused": False})
        except duckdb.Error as e:
            writes.append({"sql": sql, "refused": True, "error": type(e).__name__})
    timeout_ok, stopped_after = timeout_works(con)
    rows = con.execute("SELECT count(*) FROM fact_operation").fetchone()[0]
    raw = {"n": len(results), "passed": sum(r["ok"] for r in results), "cases": results, "read_only": writes,
           "timeout": timeout_ok, "timeout_stopped_after_s": stopped_after, "fact_rows_after": rows}
    (ROOT / "docs" / "guard_raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Перевірка захистів text-to-SQL", "",
             f"Рукописні запити подаються прямо в `guard`, без моделі. Збіг з очікуванням: {raw['passed']} з {raw['n']}.",
             "У рядках pass запит ще й виконується, а зовнішній LIMIT звіряється з очікуваним.", "",
             "| Запит | Навіщо | Очікування | Збіг | Причина |", "|---|---|---|---|---|"]
    for r in results:
        sql = r["sql"].replace("|", "/")
        lines.append(f"| `{sql}` | {r['why']} | {r['expect']} | {'так' if r['ok'] else 'ні'} | {(r['reason'] or '').replace('|', '/')} |")
    lines += ["", "## Рівень бази", "",
              "Той самий запис напряму на read-only з'єднанні, в обхід `guard`: "
              + "; ".join(f"`{w['sql']}` — {'відмова ' + w['error'] if w['refused'] else 'ВИКОНАНО'}" for w in writes)
              + f". Рядків у факті після спроб: {rows}.", "",
              f"Тайм-аут: важкий запит із чотирма CROSS JOIN при ліміті 1 с {'обірвано' if timeout_ok else 'НЕ обірвано'} через {stopped_after} с.", ""]
    (ROOT / "docs" / "guard_checks.md").write_text("\n".join(lines), encoding="utf-8")
    print(raw["passed"], "of", raw["n"], writes, timeout_ok, stopped_after, rows)
    for r in results:
        if not r["ok"]:
            print("MISS", r["sql"], r["reason"], r["output"])
    if raw["passed"] != raw["n"] or not timeout_ok or not all(w["refused"] for w in writes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
