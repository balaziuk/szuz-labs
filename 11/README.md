# ЛР11 — RAG-чат фінансових документів і графа

Пошук береться з ЛР10 (hybrid + rerank, нарізка fixed, e5-small). Граф читається з Neo4j ЛР9 лише для читання. Модель відповіді та сама, що в ЛР9/ЛР10: ключ на `gsk_` іде в Groq (`openai/gpt-oss-120b`), інакше в Gemini. Faithfulness оцінює суддя — інша модель (`qwen/qwen3.8-27b` або `gemini-2.5-flash-lite`, можна змінити через `LAB11_JUDGE_MODEL`).

## Що де лежить

- `prompts/rag_v1.md`, `prompts/rag_v2.md` — правила цитування, «не знаю», конфлікт джерел
- `prompts/judge_v1.md`, `src/judge.py` — рубрика і суддя faithfulness
- `src/rag.py` — конвеєр; відповідь із цитатою поза контекстом відхиляється
- `src/graph_context.py` — entity linking і підграф (2 кроки, ліміт ребер)
- `api/main.py`, `api/serve.py` — `POST /ask`, `GET /health`, `GET /sources/{id}`
- `src/run_all.py` — демо, порівняння з графом, метрики, оптимізація промпта, перевірка API і всі файли в `docs/`
- `eval/human_review.jsonl` — ручні оцінки; звідси береться `human_decision` у журналі

## Як запустити

Потрібен інтерпретатор ЛР10 (там FAISS і моделі), ключ у середовищі й контейнер Neo4j з ЛР9 (підключення з `9/.env`). Без Neo4j граф можна взяти з тих самих CSV: `$env:LAB11_GRAPH = "csv"`. Seed 42, temperature 0.

```powershell
docker start neo4j-lab9
..\10\.venv\Scripts\python -m pip install -r requirements.txt
..\10\.venv\Scripts\python src\run_all.py
..\10\.venv\Scripts\python -m uvicorn api.serve:app --port 8000
```

Відповіді моделей кешуються в `llm_log/cache.jsonl` (локально, у репозиторій не входить): перший прогін викликає модель, повторний відтворює ті самі файли без нових викликів. Щоб отримати нові відповіді, видаліть цей файл.

Локальні ключі API для двох ролей: `demo-public` і `demo-analyst`. Це не ключі зовнішніх сервісів.
