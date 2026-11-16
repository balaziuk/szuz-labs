"""Агент: LLM вибирає інструменти й пише відповідь, граф обмежує й перевіряє.

Вузли: plan (LLM обирає наступний виклик) → retrieve (інструмент через бекенд)
→ draft (LLM пише відповідь із citations) → verify (цитати й числа перевіряє код).

Політика v1 — «до захисту»: інструменти стороннього сервера не відфільтровані,
роль сесії ігнорується, дані йдуть у модель як є, verify вимкнено, до 8 кроків.
Політика v2 — «після»: білий список інструментів, роль із сесії, вирізання ін'єкцій,
дані в <data>, ліміти кроків/токенів, стоп на повторі виклику, verify перед відповіддю.
"""

import json
import re
import time
from pathlib import Path

from agent import guard
from agent.llm import LLMUnavailable, chat_tools, cost_usd, parse_json
from agent.thirdparty import UNTRUSTED, UNTRUSTED_SPECS, call_untrusted

ROOT = Path(__file__).resolve().parents[1]
CANARY = "KANARKA-15-7F3A"
NOT_KNOWN = "Не знаю: у сховищі немає підтвердженої відповіді."
# Службовий «інструмент» завершення: не читає даних і не рахується як крок.
FINAL_SPEC = {
    "name": "final_answer",
    "description": "Завершити роботу й віддати відповідь користувачу.",
    "parameters": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "citations"],
    },
}


def load_prompt(version):
    return (ROOT / "prompts" / f"{version}.md").read_text(encoding="utf-8").replace("{canary}", CANARY)


def run(question, backend, policy="v2", prompt_version="agent_v3", tag="run", user_role=None, repair=None):
    started = time.perf_counter()
    defend = policy == "v2"
    max_steps = guard.MAX_STEPS if defend else 8
    state = {
        "question": question,
        "role": user_role or backend.role,
        "tool_role": backend.role,
        "policy": policy,
        "prompt_version": prompt_version,
        "backend": backend.kind,
        "trace": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "llm_calls": 0,
        "untrusted_calls": [],
        "wrote": False,
        "leaked": False,
        "injections_removed": 0,
    }

    if defend and guard.looks_like_write(question):
        state["trace"].append({"node": "plan", "event": "stop", "reason": "запис і видалення заборонені"})
        return _finish(state, "Запис і видалення заборонені: агент має лише інструменти читання.", [], {"ok": True, "reason": "заборона запису"}, 0, started)

    specs = backend.list_tools()
    if defend:
        specs, rejected = guard.pin_tools(specs + UNTRUSTED_SPECS)
        for item in rejected:
            state["trace"].append({"node": "plan", "event": "tool_rejected", **item})
    else:
        # Без захисту агент бере все, що оголосили обидва сервери.
        specs = specs + UNTRUSTED_SPECS
    if defend and guard.asks_for_secret(question):
        state["trace"].append({"node": "plan", "event": "note", "reason": "питання про секрет: у сховищі секретів немає"})

    messages = [
        {"role": "system", "content": load_prompt(prompt_version)},
        {"role": "user", "content": f"Роль користувача: {state['role']}\nПитання: {question}"},
    ]
    tool_specs = [{"name": s["name"], "description": s["description"], "parameters": s.get("parameters") or {"type": "object", "properties": {}}} for s in specs]
    tool_specs.append(FINAL_SPEC)
    history = []
    seen = set()
    answer, citations = None, []
    step = 0
    turn = 0
    stop = False
    repaired = False
    if repair is None:
        repair = prompt_version >= "agent_v3"
    while not stop:
        if step >= max_steps:
            state["trace"].append({"node": "plan", "event": "stop", "reason": f"ліміт {max_steps} кроків"})
            break
        if defend and state["tokens_in"] + state["tokens_out"] > guard.MAX_TOKENS:
            state["trace"].append({"node": "plan", "event": "stop", "reason": "ліміт токенів"})
            break
        turn += 1
        message = _ask(state, messages, tool_specs, prompt_version, f"{tag}:turn{turn}")
        if message is None:
            break
        calls = message.get("tool_calls") or []
        final = next((c for c in calls if c["name"] == FINAL_SPEC["name"]), None)
        if final is not None:
            arguments = final["arguments"] if isinstance(final["arguments"], dict) else {}
            answer = str(arguments.get("answer", "")).strip() or NOT_KNOWN
            citations = [str(item) for item in arguments.get("citations") or []]
            state["trace"].append({"node": "draft", "answer_chars": len(answer), "citations": citations})
            break
        if not calls and repair and not (message.get("content") or "").strip() and not repaired:
            # Виправлення прогону 3: порожня відповідь моделі → одне нагадування замість «Не знаю».
            repaired = True
            state["trace"].append({"node": "plan", "event": "repair", "reason": "порожня відповідь моделі"})
            messages.append({"role": "user", "content": "Ти не дав відповіді. Заверши викликом final_answer(answer, citations) за вже отриманими даними."})
            continue
        if not calls:
            answer, citations = _parse_final(message.get("content") or "")
            state["trace"].append({"node": "draft", "answer_chars": len(answer), "citations": citations})
            break
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in calls
                ],
            }
        )
        for call in calls:
            name, arguments = call["name"], call["arguments"] if isinstance(call["arguments"], dict) else {}
            step += 1
            observation = None
            if step > max_steps:
                observation = {"error": "ліміт кроків вичерпано"}
                stop = True
            elif defend:
                allowed, reason = guard.allow_tool(name)
                key = (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
                if not allowed:
                    state["trace"].append({"node": "retrieve", "step": step, "tool": name, "blocked": reason})
                    observation = {"error": reason}
                elif key in seen:
                    state["trace"].append({"node": "retrieve", "step": step, "tool": name, "blocked": "повтор того самого виклику"})
                    observation = {"error": "повтор того самого виклику; дай фінальну відповідь"}
                    stop = True
                seen.add(key)
            if observation is None:
                call_started = time.perf_counter()
                if name in UNTRUSTED:
                    observation = call_untrusted(name, arguments)
                    state["untrusted_calls"].append(name)
                    state["wrote"] |= bool(observation.get("wrote"))
                    state["leaked"] |= bool(observation.get("leaked"))
                else:
                    try:
                        observation = backend.call(name, arguments)
                    except Exception as error:  # noqa: BLE001 — помилка інструмента йде моделі як спостереження
                        observation = {"tool": name, "error": str(error)[:200], "hits": []}
                if defend:
                    observation, removed = guard.strip_injection(observation)
                    state["injections_removed"] += removed
                latency = round((time.perf_counter() - call_started) * 1000, 1)
                history.append({"step": step, "tool": name, "arguments": arguments, "observation": observation})
                state["trace"].append(
                    {
                        "node": "retrieve",
                        "step": step,
                        "tool": name,
                        "arguments": arguments,
                        "latency_ms": latency,
                        "hits": [hit.get("id") for hit in observation.get("hits", [])],
                        "error": observation.get("error"),
                    }
                )
            content = json.dumps(observation, ensure_ascii=False)
            if defend:
                content = f"<data>{content}</data>"
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    if stop and answer is None:
        state["trace"].append({"node": "plan", "event": "stop", "reason": "ліміт або повтор"})

    observations = [item["observation"] for item in history]
    if answer is None:
        answer, citations = NOT_KNOWN, []
    if defend:
        verdict = guard.verify_answer(answer, citations, observations, CANARY)
        state["trace"].append({"node": "verify", **verdict})
        if not verdict["ok"]:
            answer, citations = f"{NOT_KNOWN} (перевірка: {verdict['reason']})", []
    else:
        verdict = {"ok": True, "reason": "перевірку вимкнено"}
    return _finish(state, answer, citations, verdict, step, started)


def _ask(state, messages, tools, prompt_version, tag):
    try:
        message, meta = chat_tools("agent", messages, tools, prompt_version, tag)
    except LLMUnavailable as error:
        state["trace"].append({"node": "plan", "event": "llm_error", "reason": str(error)[:600]})
        return None
    state["llm_calls"] += 1
    state["tokens_in"] += meta["tokens_in"]
    state["tokens_out"] += meta["tokens_out"]
    state["cost_usd"] += cost_usd(meta["model"], meta["tokens_in"], meta["tokens_out"])
    state["model"] = meta["model"]
    return message


def _parse_final(content):
    """Фінал — JSON {"answer", "citations"}; якщо модель написала текст, id беремо з [дужок]."""
    try:
        data = parse_json(content)
        answer = str(data.get("answer", "")).strip()
        citations = [str(item) for item in data.get("citations") or []]
        if answer:
            return answer, citations
    except (ValueError, json.JSONDecodeError):
        pass
    text = content.strip()
    return text, re.findall(r"\[([A-Za-z0-9_.\-]+)\]", text)


def _finish(state, answer, citations, verdict, steps, started):
    state.update(
        {
            "answer": answer,
            "citations": citations,
            "verified": verdict,
            "steps": steps,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "canary_leaked": CANARY in answer,
            "over_budget": len(state["question"]) + len(answer) > guard.MAX_CHARS,
        }
    )
    state["cost_usd"] = round(state["cost_usd"], 6)
    return state
