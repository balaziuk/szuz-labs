# ЛР16. Рекомендації і демонстратор

Рекомендації читають каталог і золотий набір ЛР13 та не змінюють ЛР8, ЛР9 і ЛР11. Користувачі синтетичні.

## Передумови

- Python 3.12
- каталоги `szuz-labs/9/data`, `szuz-labs/13/data`, `szuz-labs/15`
- для технічної записки: `pip install -r requirements.txt` (reportlab)
- ключ API не обов'язковий: перефразування пояснень (Groq, `GROQ_API_KEY` або `GEMINI_API_KEY` з ключем `gsk_…`) і агент ЛР15 читають кеш `llm_log/explain_cache.jsonl` та `15/llm_log/cache.jsonl`; без ключа й кешу показується речення шляху
- `SZUZ_LABS` потрібна лише в контейнері, там вона дорівнює `/labs`

## Одна команда

```text
python reco/run_all.py
python demo/run_demo.py
```

Перша команда будує `data/interactions.csv` (seed 42), рахує метрики, пояснення, холодний старт і `docs/whitepaper.pdf`. Друга проганяє п'ять кроків демо і пише `docs/demo_log.txt`.

Тести даних: після `run_all` файл `docs/reco_eval.md` має містити чотири конфігурації і розділ «Фільтри». `docs/cold_start.md` має містити п'ять пояснень.

## Docker

`docker-compose.yml` збирає образ з контекстом `szuz-labs` і запускає той самий `demo/run_demo.py`. Лог збірки й запуску — `docs/docker_log.txt`. Друга машина цей каталог не піднімала.

## Що всередині

- `reco/recommend.py` — популярність, граф, триграмний kNN, RRF
- `reco/eval.py` — часове розбиття і п'ять метрик
- `reco/explain.py` — речення зі шляху, LLM-перефразування (промпт explain_v1) і дві перевірки: лапки та відсутність сутностей поза шляхом; частка — `data/explain_eval.json`
- `docs/demo_script.md` — сім хвилин, п'ять запитів, є «не знаю» і атака
