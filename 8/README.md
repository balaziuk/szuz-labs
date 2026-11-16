# ЛР8 — RDF-сховище фінансових операцій

Онтологія з ЛР7, наповнена даними й піднята в Apache Jena Fuseki. Тут SPARQL-запити, UPDATE,
RDFS-виведення, SHACL-перевірка й експорт у JSON-LD.

## Що де лежить

- `vocabulary.ttl` — словник (класи й властивості)
- `data.ttl` — дані, генерує `build_data.py`
- `source_graph.trig` — іменований граф з джерелом даних
- `queries.rq`, `updates.rq` — SPARQL-запити та оновлення
- `shapes.ttl` + `valid_example.ttl` / `invalid_example.ttl` — SHACL
- `run_*.py` — запускають запити, оновлення, виведення й SHACL локально через rdflib
- `export_jsonld.py` — те саме в JSON-LD

## Як запустити

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python build_data.py
.\.venv\Scripts\python run_queries.py
.\.venv\Scripts\python run_updates.py
.\.venv\Scripts\python run_inference.py
.\.venv\Scripts\python run_shacl.py
```

З Fuseki: покласти Fuseki 5.2 у `C:\fuseki-lab8` (шлях без кирилиці), далі `.\start_fuseki.ps1`
(або `-Rdfs` з виведенням) і `run_fuseki_demo.py`. UI на http://localhost:3030, датасет `fin`.
