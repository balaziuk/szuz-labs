# ЛР9 — граф фінансових операцій у Neo4j

Ті самі фінансові дані, що й у ЛР7–8 (рахунки, операції, категорії, бюджети, ризики), тільки тепер
як граф у Neo4j. Тут імпорт з CSV, кілька Cypher-запитів, PageRank/Louvain, порівняння з SPARQL з ЛР8
і спроба генерувати Cypher через LLM.

## Що де лежить

- `src/build_data.py` — генерує CSV у `data/` (вересень–жовтень з ЛР8, решта місяців випадкові)
- `import/` — обмеження, індекси та імпорт CSV у Neo4j
- `queries/` — 10 запитів (витрати, бюджети, контрагенти, ланцюжки впливу)
- `gds/` — PageRank і Louvain
- `src/run_*.py` — запускають усе це з Python
- `src/sparql_vs_cypher.py` — ті самі питання в SPARQL і Cypher, порівнює відповіді
- `src/t2c.py` — питання українською → Cypher через LLM, перевірка з `tests/t2c_gold.jsonl`

## Як запустити

Потрібен Docker і Python 3.12.

```powershell
docker run -d --name neo4j-lab9 -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/<пароль> -e NEO4J_PLUGINS='["graph-data-science"]' `
  -e NEO4J_dbms_security_procedures_unrestricted='gds.*' neo4j:5.26

python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # вписати пароль

.\.venv\Scripts\python src/build_data.py
Get-ChildItem data\*.csv | ForEach-Object { docker cp $_.FullName neo4j-lab9:/var/lib/neo4j/import/ }
.\.venv\Scripts\python src/run_cypher.py import/01_constraints.cypher import/02_import.cypher

.\.venv\Scripts\python src/run_queries.py
.\.venv\Scripts\python src/run_gds.py
```

Для `sparql_vs_cypher.py` має працювати Fuseki з ЛР8. Для `t2c.py` потрібен ключ у
`GROQ_API_KEY` або `GEMINI_API_KEY`, далі `python src/t2c.py v1` (або `v2`).
