"""Виклик LLM для агента і для червоної команди.

Ключ береться з GEMINI_API_KEY або GROQ_API_KEY і нікуди не пишеться.
Кожен виклик іде в llm_log/agent.jsonl. Той самий запит удруге береться з
llm_log/cache.jsonl, тож повторний прогін API не чіпає.
"""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "llm_log" / "agent.jsonl"
CACHE = ROOT / "llm_log" / "cache.jsonl"

TEMPERATURE = 0.0
# Змінюється разом із параметрами запиту, щоб кеш не віддавав старі відповіді.
PARAMS_VERSION = "p2"
SEED = 42
# Мозок агента і червона команда — різні моделі.
GEMINI = {"agent": "gemini-2.5-flash-lite", "redteam": "gemini-2.5-flash"}
GROQ = {"agent": "openai/gpt-oss-120b", "redteam": "qwen/qwen3.8-27b"}
# Номінальна ціна за 1 млн токенів (вхід, вихід), USD; безкоштовний рівень коштує 0.
PRICE = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
}
# Groq free tier: 8000 токенів/хв для gpt-oss-120b, виклик агента ~1200 токенів → ~6 викликів/хв.
MIN_GAP = float(os.environ.get("LAB15_MIN_GAP", "10"))

_lock = threading.Lock()
_last_call = [0.0]
_cache = None


class LLMUnavailable(RuntimeError):
    pass


def _key():
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip().strip('"')
    if not key:
        raise LLMUnavailable("GEMINI_API_KEY / GROQ_API_KEY не задано")
    return key


def model_for(role):
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip().strip('"')
    # Без ключа — моделі Groq: кеш llm_log/cache.jsonl наповнено ними, і ключ кешу містить назву моделі.
    table = GEMINI if key and not key.startswith("gsk_") else GROQ
    return os.environ.get(f"LAB15_{role.upper()}_MODEL", table[role])


def cost_usd(model, tokens_in, tokens_out):
    price_in, price_out = PRICE.get(model, (0.0, 0.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def _load_cache():
    global _cache
    if _cache is None:
        _cache = {}
        if CACHE.exists():
            for line in CACHE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    _cache[row["key"]] = row
    return _cache


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _http(model, system, prompt):
    key = _key()
    if key.startswith("gsk_"):
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {
            "model": model,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "lab15-agent/1.0"}

        def pick(data):
            usage = data.get("usage") or {}
            return data["choices"][0]["message"]["content"], usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": TEMPERATURE, "seed": SEED, "responseMimeType": "application/json"},
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}

        def pick(data):
            usage = data.get("usageMetadata") or {}
            parts = data["candidates"][0]["content"]["parts"]
            texts = [part["text"] for part in parts if part.get("text") and not part.get("thought")]
            return (texts[-1] if texts else ""), usage.get("promptTokenCount") or 0, usage.get("candidatesTokenCount") or 0

    return pick(_post(url, body, headers))


def _post(url, body, headers):
    """POST з паузою між викликами й повторами на 429/5xx."""
    body = dict(body)
    daily_waits = 0
    attempt = 0
    while attempt < 8:
        with _lock:
            wait = MIN_GAP - (time.monotonic() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.monotonic()
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        attempt += 1
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:600]
            retry_after = error.headers.get("retry-after") if error.headers else None
            if error.code == 429 and "per day" in detail and daily_waits < 200:
                # Денний ліміт токенів (ковзне вікно): чекаємо, скільки просить провайдер; спроба не рахується.
                daily_waits += 1
                attempt -= 1
                try:
                    pause = float(retry_after) + 5 if retry_after else 120
                except ValueError:
                    pause = 120
                print(f"    [денний ліміт LLM, чекаю {pause:.0f} с]", flush=True)
                time.sleep(min(pause, 1800))
                continue
            if error.code in (429, 500, 503) and attempt < 8:
                try:
                    pause = max(float(retry_after) + 1, 10 * attempt) if retry_after else 15 * attempt
                except ValueError:
                    pause = 15 * attempt
                time.sleep(min(pause, 90))
                continue
            if error.code == 400 and ("json_validate_failed" in detail or "tool_use_failed" in detail) and attempt < 6:
                # Groq інколи відкидає власну генерацію (невалідний JSON чи виклик) — повтор; без json-режиму.
                body.pop("response_format", None)
                continue
            raise LLMUnavailable(f"LLM HTTP {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < 6:
                time.sleep(5)
                continue
            raise LLMUnavailable(str(error)) from None
    raise LLMUnavailable("вичерпано повтори")


def _openai_endpoint():
    key = _key()
    if key.startswith("gsk_"):
        return "https://api.groq.com/openai/v1/chat/completions", key
    # Gemini має OpenAI-сумісний ендпоінт із тим самим форматом tools.
    return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", key


def chat_tools(role, messages, tools, prompt_version, tag):
    """Один крок агента з нативним викликом функцій (OpenAI-формат).

    Повертає (message, meta): message = {"content": str, "tool_calls": [{"id", "name", "arguments"}]}.
    """
    model = model_for(role)
    payload = [model, PARAMS_VERSION, prompt_version, messages, tools]
    key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    cache = _load_cache()
    if key in cache:
        row = cache[key]
        cached = True
    else:
        url, api_key = _openai_endpoint()
        body = {
            "model": model,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "messages": messages,
            "tools": [{"type": "function", "function": spec} for spec in tools],
            "tool_choice": "auto",
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "User-Agent": "lab15-agent/1.0"}
        data = _post(url, body, headers)
        message = data["choices"][0]["message"]
        calls = []
        for call in message.get("tool_calls") or []:
            raw_args = call["function"].get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                arguments = {"_raw": raw_args}
            calls.append({"id": call.get("id") or f"call_{len(calls)}", "name": call["function"]["name"], "arguments": arguments})
        usage = data.get("usage") or {}
        row = {
            "key": key,
            "model": model,
            "raw": json.dumps({"content": message.get("content") or "", "tool_calls": calls}, ensure_ascii=False),
            "tokens_in": usage.get("prompt_tokens") or 0,
            "tokens_out": usage.get("completion_tokens") or 0,
        }
        cache[key] = row
        _append(CACHE, row)
        cached = False
    message = json.loads(row["raw"])
    meta = {"model": model, "tokens_in": row["tokens_in"], "tokens_out": row["tokens_out"], "cached": cached}
    _append(
        LOG,
        {
            "date": datetime.now(timezone.utc).isoformat(),
            "tag": tag,
            "role": role,
            "model": model,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "prompt_version": prompt_version,
            "messages": len(messages),
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "cached": cached,
            "raw": row["raw"],
            "parse_error": None,
            "human_decision": None,
        },
    )
    return message, meta


def parse_json(raw):
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("у відповіді немає JSON-об'єкта")
    return json.loads(text[start : end + 1])


def ask_json(role, system, prompt, prompt_version, tag):
    """Повертає (dict, meta). meta містить модель, токени, чи був кеш."""
    model = model_for(role)
    key = hashlib.sha256(json.dumps([model, PARAMS_VERSION, prompt_version, system, prompt], ensure_ascii=False).encode("utf-8")).hexdigest()
    cache = _load_cache()
    if key in cache:
        row = cache[key]
        raw, tokens_in, tokens_out, cached = row["raw"], row["tokens_in"], row["tokens_out"], True
    else:
        raw, tokens_in, tokens_out = _http(model, system, prompt)
        cached = False
        row = {"key": key, "model": model, "raw": raw, "tokens_in": tokens_in, "tokens_out": tokens_out}
        cache[key] = row
        _append(CACHE, row)
    try:
        data = parse_json(raw)
        error = None
    except (ValueError, json.JSONDecodeError) as exc:
        data, error = None, str(exc)
    meta = {"model": model, "tokens_in": tokens_in, "tokens_out": tokens_out, "cached": cached, "parse_error": error}
    _append(
        LOG,
        {
            "date": datetime.now(timezone.utc).isoformat(),
            "tag": tag,
            "role": role,
            "model": model,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "prompt_version": prompt_version,
            "prompt_chars": len(system) + len(prompt),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cached": cached,
            "raw": raw,
            "parse_error": error,
            "human_decision": None,
        },
    )
    return data, meta
