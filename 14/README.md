# ЛР14 — якість сховища фінансових операцій

Сховище те саме, що в ЛР8 (Turtle) і ЛР9 (CSV-граф). Нічого в тих каталогах цей код не переписує: копія з походженням лягає в `quality/store_after.ttl`.

## Що де лежить

- `quality/profile.py` — вісім з гаком метрик, пороги, вибірка 30 записів, три пріоритети
- `quality/dedup.py`, `quality/pairs_gold.csv` — blocking, рядок, ембединг тріграм (crc32, відтворюваний), ЄДРПОУ; поріг лише на dev
- `quality/llm_judge.py` — LLM-суддя на спірних парах (смуга 0.30–0.70), журнал `llm_log/judge.jsonl`, кеш `llm_log/judge_cache.jsonl`
- `quality/conflicts.md`, `quality/alternatives.json` — п'ять суперечностей і дві збережені альтернативи
- `quality/shapes.ttl` (pyshacl), `quality/operation.schema.json`, `quality/gate.py` — 12 перевірок чотирьох типів, звіт `quality/gate_log.md`, тренд `quality/gate_trend.csv`; `gate.py --inject amount|account|budget` має завершитись кодом 1
- `quality/tests/` — pytest
- `quality/after_report.md`, `quality/rag_probe.json` — до/після, метрики RAG ЛР11 і цільовий прогін графового лінкера ЛР11
- `claims/claims.csv` — таблиця тверджень
- `../.github/workflows/quality.yml` (корінь репозиторію `szuz-labs`) — gate, перевірка навмисних дефектів і pytest у CI; потрібні закомічені `8/data.ttl` і `9/data/*.csv`

## Як запустити

Python 3.12. Ключ API потрібен лише для першого прогону судді (`GROQ_API_KEY` або `GEMINI_API_KEY`); далі рішення беруться з `llm_log/judge_cache.jsonl`. Без ключа й кешу дедуплікація працює за порогом.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python quality\run_all.py
```

Seed вибірки точності — 42. Дата baseline — 2026-11-03.
