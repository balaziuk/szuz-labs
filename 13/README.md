# ЛР13 — видобування знань із текстів

Ті самі рахунки, контрагенти, категорії й ризики, що в ЛР9. Корпус — 23 короткі нотатки хаба (виписки, картки реєстру, ліміти, ризики). Золотий набір зібраний разом із текстами, офсети перевіряє скрипт. Метод А порівнюється з методом Б на test (d15–d23); шаблони методу А заморожені на dev.

## Що де лежить

- `docs/extraction_schema.md` — типи, правила розмітки, JSON, нормалізація, пілот із п'ятьма уточненнями
- `data/gold.jsonl`, `data/annotator_b.jsonl`, `docs/gold_card.md` — золотий набір, другий прохід і картка
- `src/extract_rules.py` — метод А: словник ЛР9 і регулярні вирази; spaCy підключається, якщо імпорт проходить
- `src/extract_llm.py`, `prompts/extract_v1.md` — метод Б: закритий словник, evidence, до двох повторів
- `docs/extraction_eval.md` — P/R/F1, частка без цитати, вартість, розбір помилок
- `data/graph_load.ttl`, `data/graph_load.cypher`, `docs/linking.md` — зв'язані сутності з походженням
- `docs/patterns.md` — асоціативні правила і рішення, що з них лишати
- `llm_log/` — сирі відповіді моделі; `claims/claims.csv` — перевірені твердження

## Як запустити

Python 3.12. Ключ API не в коді: для методу Б потрібен `GEMINI_API_KEY` або `GROQ_API_KEY` у середовищі. Temperature 0, seed 42. Повторний запуск методу Б читає `llm_log/cache.jsonl` і API не викликає.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m spacy download uk_core_news_sm
.\.venv\Scripts\python src\run_all.py
```

Без моделі й без ключа:

```powershell
.\.venv\Scripts\python src\run_all.py --no-llm
```

На цій машині імпорт spaCy зупиняє політика Application Control (`gold_io.pyd`). Метод А тоді працює тим самим словником і регулярними виразами, без статистичного NER. Якщо `import spacy` проходить, скрипт ставить EntityRuler поверх `uk_core_news_sm` або порожньої української моделі. Мітки PER/ORG/LOC у предикт не пишуться: вони не збігаються з типами схеми, це зафіксовано в `docs/dev_tuning.md`.

У граф Neo4j з ЛР9 нічого не завантажується. Доказ завантаження — SPARQL по `data/graph_load.ttl` у `docs/linking.md`. Cypher для окремої бази лежить у `data/graph_load.cypher`.
