# ЛР12 — аналітична зірка фінансових операцій

Ті самі рахунки, категорії й контрагенти, що в ЛР9. Генератор (`etl/generate.py`, seed 42)
розгортає місячний шаблон на 2023-01 … 2026-10, щоб у факті було понад 1000 операцій.
Далі — зірка в DuckDB, OLAP, семантичний шар і text-to-SQL.

## Що де лежить

- `sql/ddl.sql`, `sql/views.sql` — схема і подання `v_operation`
- `etl/generate.py`, `etl/load.py` — генератор, Parquet, перевірки якості
- `sql/olap/` — ROLLUP, CUBE, slice, dice, pivot, вікна, drill-down
- `semantic/metrics.yml`, `src/metrics.py` — метрики і SQL за назвою
- `src/t2sql.py`, `tests/t2sql.jsonl`, `tests/t2sql_holdout.jsonl` — text-to-SQL з перевіркою AST; відповіді моделі кешуються локально в `llm_log/t2sql.jsonl` (у репозиторій не входить), повторний запуск не викликає API
- `src/check_guard.py`, `tests/guard_cases.jsonl` — захисти на рукописних запитах, без моделі
- `dashboard/` — чотири графіки й інтерпретації

## Як запустити

Python 3.12. Ключ API не в коді: для text-to-SQL потрібен `GEMINI_API_KEY` або `GROQ_API_KEY` у середовищі.
Seed генератора й LLM — 42. Temperature text-to-SQL — 0.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

$env:MPLBACKEND = "Agg"
.\.venv\Scripts\python etl\load.py
.\.venv\Scripts\python src\run_olap.py
.\.venv\Scripts\python src\metrics.py
.\.venv\Scripts\python dashboard\build.py
.\.venv\Scripts\python src\check_guard.py
.\.venv\Scripts\python src\t2sql.py
```
