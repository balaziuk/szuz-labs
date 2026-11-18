"""LLM-суддя дублікатів: для спірної пари повертає рішення й пояснення.

Ключ — GROQ_API_KEY або GEMINI_API_KEY (Groq-ключ gsk_… теж може лежати в GEMINI_API_KEY).
Кожен виклик пишеться в llm_log/judge.jsonl; відповідь кешується в llm_log/judge_cache.jsonl,
тож повторний прогін API не чіпає. Без ключа й без кешу суддя повертає None — рішення лишається за порогом.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "llm_log" / "judge.jsonl"
CACHE = ROOT / "llm_log" / "judge_cache.jsonl"
PROMPT_VERSION = "judge_v1"
TEMPERATURE = 0.0
SEED = 42
GROQ_MODEL = os.environ.get("LAB14_JUDGE_MODEL", "qwen/qwen3.8-27b")
GEMINI_MODEL = os.environ.get("LAB14_JUDGE_MODEL", "gemini-2.5-flash")

PROMPT = """Ти — експерт з даних про контрагентів (українські банки, постачальники, ФОП).
Визнач, чи два записи описують ту саму організацію. Враховуй відмінки, розмовні скорочення,
організаційно-правову форму (ТОВ, ПрАТ, АТ, ФОП). Різні коди ЄДРПОУ означають різні організації;
порожній код нічого не доводить.

Запис A: назва «{left_name}», ЄДРПОУ: {left_code}
Запис B: назва «{right_name}», ЄДРПОУ: {right_code}

Поверни лише JSON: {{"duplicate": true|false, "confidence": 0..1, "explanation": "одне речення українською"}}"""


def _key():
    return (os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip().strip('"')


def _cache():
    if not CACHE.exists():
        return {}
    return {row["key"]: row for row in (json.loads(x) for x in CACHE.read_text(encoding="utf-8").splitlines() if x.strip())}


def _previous_review(pair_id, raw):
    """Рішення людини з попереднього запису тієї ж пари з тим самим сирим виходом (кеш)."""
    if not LOG.exists():
        return None, None
    found = (None, None)
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("pair_id") == pair_id and rec.get("raw_output") == raw and rec.get("human_decision"):
            found = (rec["human_decision"], rec.get("human_note"))
    return found


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _call(prompt):
    key = _key()
    if key.startswith("gsk_"):
        model = GROQ_MODEL
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "lab14-judge/1.0"}
    else:
        model = GEMINI_MODEL
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    body = {
        "model": model,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(6):
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            usage = data.get("usage") or {}
            return model, data["choices"][0]["message"]["content"], usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 503) and attempt < 5:
                retry = error.headers.get("retry-after") if error.headers else None
                time.sleep(min(float(retry) + 2 if retry else 15 * (attempt + 1), 120))
                continue
            raise RuntimeError(f"LLM HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from None
    raise RuntimeError("вичерпано повтори")


def judge(left, right, pair_id):
    """left/right: {"name", "edrpou"}. Повертає dict або None, якщо судді немає."""
    prompt = PROMPT.format(left_name=left["name"], left_code=left["edrpou"] or "немає", right_name=right["name"], right_code=right["edrpou"] or "немає")
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, prompt], ensure_ascii=False).encode("utf-8")).hexdigest()
    cache = _cache()
    if key in cache:
        row, cached = cache[key], True
    elif _key():
        model, raw, tokens_in, tokens_out = _call(prompt)
        row, cached = {"key": key, "model": model, "raw": raw, "tokens_in": tokens_in, "tokens_out": tokens_out}, False
        _append(CACHE, row)
    else:
        return None
    try:
        text = row["raw"]
        verdict = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        verdict = {"duplicate": None, "confidence": 0, "explanation": "невалідний JSON"}
    decision, note = _previous_review(pair_id, row["raw"]) if cached else (None, None)
    _append(
        LOG,
        {
            "date": datetime.now(timezone.utc).isoformat(),
            "pair_id": pair_id,
            "model": row["model"],
            "temperature": TEMPERATURE,
            "seed": SEED,
            "prompt_version": PROMPT_VERSION,
            "prompt": prompt,
            "raw_output": row["raw"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "cached": cached,
            "human_decision": decision,
            "human_note": note,
        },
    )
    return {"duplicate": verdict.get("duplicate"), "confidence": verdict.get("confidence"), "explanation": verdict.get("explanation", ""), "model": row["model"]}
