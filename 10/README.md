# ЛР10 — семантичний пошук по фінансових документах

Корпус зі статей Вікіпедії про фінанси плюс звіти з попередніх лаб. Його ріжемо на фрагменти,
будуємо векторні індекси (FAISS) і порівнюємо звичайний векторний пошук із гібридним (BM25 + вектори + reranker).

## Що де лежить

- `src/fetch_corpus.py`, `src/build_corpus.py` — завантаження й очищення корпусу → `data/`
- `src/chunking.py` — три способи нарізки (фіксована, за структурою, семантична)
- `src/index.py` — індекси для двох моделей embeddings
- `src/hybrid.py` — гібридний пошук і reranker
- `src/gen_questions.py`, `src/curate_gold.py` — тестові питання → `eval/gold.jsonl`
- `src/evaluate.py` — метрики якості пошуку
- `src/make_annotation.py`, `src/kappa.py` — друга розмітка й узгодженість між розмітниками
- `src/checks.py` — додаткові перевірки: обрізання MiniLM, бутстреп, pre-filter, upsert/delete/rebuild

## Як запустити

Версії залежностей зафіксовано в `requirements.txt`. Параметри LLM: temperature 0.3, seed 42
(`src/gen_questions.py`); бутстреп у `src/checks.py` теж використовує seed 42.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\pip install -r requirements.txt

.\.venv\Scripts\python src/fetch_corpus.py
.\.venv\Scripts\python src/build_corpus.py
.\.venv\Scripts\python src/gen_questions.py
.\.venv\Scripts\python src/curate_gold.py
.\.venv\Scripts\python src/chunking.py
.\.venv\Scripts\python src/index.py
.\.venv\Scripts\python src/hybrid.py
.\.venv\Scripts\python src/evaluate.py
.\.venv\Scripts\python src/checks.py
```

Розмітка для κ запускається окремо: `src/make_annotation.py` створює порожній
`annotation/annotation_B.csv`, другий розмітник заповнює його за `annotation/ІНСТРУКЦІЯ.md`, а
`src/kappa.py` рахує результат. Повторний запуск `make_annotation.py` перезаписує готову розмітку.

`build_corpus.py` читає звіти з `../../labs` і аналітику з `../9/docs`. Цих файлів у репозиторії
немає, тому на чистому клоні крок `build_corpus.py` пропускається: готові `data/documents.jsonl` і
`data/corpus.jsonl` уже лежать у репозиторії, решта кроків працює з них. Моделі завантажуються з
Hugging Face при першому запуску. Для `gen_questions.py` потрібен ключ у `GROQ_API_KEY`; він
перезаписує журнал `llm_log/gen_questions.jsonl`, а `curate_gold.py` містить ручні рішення щодо
кандидатів, тому новий запуск LLM потребує нового перегляду.
