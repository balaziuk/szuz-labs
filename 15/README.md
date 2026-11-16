# ЛР15. LLM-агент з інструментами над сховищем знань

Агент на LLM (`openai/gpt-oss-120b` через Groq) відповідає на питання про хаб фінансових операцій, викликаючи три інструменти читання через MCP-сервер. Відповідь проходить перевірку цитат. Запис нових знань іде окремо — через `propose_fact` і людину.

## Запуск з нуля

Потрібні Python 3.12 і каталоги `szuz-labs/9/data` та `szuz-labs/13/data`.

```text
cd szuz-labs/15
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
set GROQ_API_KEY=...               # або GEMINI_API_KEY; ключ не зберігається в коді й журналах
python agent/redteam.py            # атаки від червоної команди (інша модель)
python agent/run_all.py            # MCP-демо, сценарії, атаки, HITL, документи
```

Seed 42, temperature 0. Усі відповіді моделей кешуються в `llm_log/cache.jsonl`, тож повторний `run_all.py` відтворює ті самі результати без звернень до API. Щоб прогнати наново, видаліть кеш.

Окремо:

```text
python mcp_server/server.py                                  # MCP-сервер (stdio), роль з LAB15_ROLE
python agent/propose_fact.py propose "{\"id\":\"f1\",\"kind\":\"alias\",\"source\":\"d17\",\"proposed_by\":\"me\",\"payload\":{\"surface\":\"Приват\",\"target\":\"Cp_PrivatBank\"}}"
python agent/propose_fact.py review f1 approve "власник"
python agent/propose_fact.py metrics
```

Підключення до IDE: `.mcp.json` (Claude Code / Claude Desktop) запускає той самий сервер з роллю analyst.

## Що де лежить

| результат | артефакти |
| --- | --- |
| 1. Специфікація | `docs/agent_spec.md` |
| 2. Реалізація | `mcp_server/server.py`, `agent/graph.py`, `agent/backend.py`, `agent/tools.py`, `agent/llm.py`, `docs/mcp_demo.md`, `data/traces.jsonl` |
| 3. Сценарні тести | `tests/agent_scenarios.jsonl`, `docs/agent_eval.md`, `prompts/agent_v1.md` → `prompts/agent_v2.md` |
| 4. Безпека | `tests/attacks.jsonl`, `tests/attacks_redteam.jsonl`, `agent/redteam.py`, `agent/guard.py`, `agent/thirdparty.py`, `docs/agent_security.md` |
| 5. Людина в циклі | `agent/propose_fact.py`, `agent/fact_shapes.ttl`, `data/audit.jsonl`, `data/kb_accepted.ttl`, `docs/hitl.md` |
| протокол «LLM-експерт» | `llm_log/agent.jsonl`, `llm_log/cache.jsonl`, `llm_log/summary.json`, `claims/claims.csv` |

`agent/thirdparty.py` — навмисно небезпечний «сторонній сервер» (довільний SQL, отруєний опис) для атак до захисту; виконується лише на копії даних у пам'яті.
