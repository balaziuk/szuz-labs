import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPERATURE = 0.0
SEED = 42
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_JUDGE = "gemini-2.5-flash-lite"
GROQ_JUDGE = "qwen/qwen3.8-27b"


def api_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY / GROQ_API_KEY не задано")
    return key.strip().strip('"')


def call_llm(prompt, judge=False):
    key = api_key()
    if key.startswith("gsk_"):
        groq_model = os.environ.get("LAB11_JUDGE_MODEL", GROQ_JUDGE) if judge else GROQ_MODEL
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {"model": groq_model, "temperature": TEMPERATURE, "seed": SEED,
                "messages": [{"role": "user", "content": prompt}]}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                   "User-Agent": "lab11-rag/1.0"}

        def pick(data):
            usage = data.get("usage") or {}
            return data["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens"), groq_model
    else:
        gemini_model = os.environ.get("LAB11_JUDGE_MODEL", GEMINI_JUDGE) if judge else GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": TEMPERATURE, "seed": SEED}}
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}

        def pick(data):
            usage = data.get("usageMetadata") or {}
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), gemini_model
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return pick(json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(12 * (attempt + 1))
                continue
            raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None


def log_row(row, auto_decision, reason, human_decision):
    return {
        "date": datetime.now(timezone.utc).isoformat(),
        "id": row["id"],
        "model": row["model"],
        "temperature": TEMPERATURE,
        "seed": SEED,
        "prompt_version": row["prompt_version"],
        "question": row["question"],
        "sources": row["sources"],
        "prompt": row["prompt"],
        "raw_output": row["raw_answer"],
        "answer": row["answer"],
        "auto_decision": auto_decision,
        "reason": reason,
        "human_decision": human_decision,
        "judge_model": row.get("judge_model"),
        "judge_score": row.get("faithfulness"),
        "judge_reason": row.get("judge_reason"),
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "latency_ms": row["latency_ms"],
        "retrieval_ms": row["retrieval_ms"],
        "llm_ms": row["llm_ms"],
        "cached": row["cached"],
    }
