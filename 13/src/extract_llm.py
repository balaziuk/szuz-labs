"""Метод Б: LLM, закритий словник типів, цитата evidence, до двох повторів після помилки.

Ключ береться зі середовища (GEMINI_API_KEY або GROQ_API_KEY) і в журнал не пишеться.
Повторний запуск читає llm_log/cache.jsonl і API не чіпає.
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schema import ENTITY_TYPES, RELATION_TYPES

PROMPT_VERSION = "extract_v1"
TEMPERATURE = 0.0
SEED = 42
MAX_ATTEMPTS = 3
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"


def load_cache():
    path = ROOT / "llm_log" / "cache.jsonl"
    cache = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                cache[row["key"]] = row
    return cache


def append_jsonl(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def call_llm(prompt):
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip().strip('"')
    if not key:
        raise SystemExit("GEMINI_API_KEY / GROQ_API_KEY не задано")
    if key.startswith("gsk_"):
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {
            "model": GROQ_MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "lab13-extract/1.0",
        }

        def pick(data):
            usage = data.get("usage") or {}
            return (
                data["choices"][0]["message"]["content"],
                usage.get("prompt_tokens") or 0,
                usage.get("completion_tokens") or 0,
                GROQ_MODEL,
            )
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": TEMPERATURE,
                "seed": SEED,
                "responseMimeType": "application/json",
            },
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}

        def pick(data):
            usage = data.get("usageMetadata") or {}
            parts = data["candidates"][0]["content"]["parts"]
            texts = [part["text"] for part in parts if part.get("text") and not part.get("thought")]
            text = texts[-1] if texts else parts[-1].get("text", "")
            return text, usage.get("promptTokenCount") or 0, usage.get("candidatesTokenCount") or 0, GEMINI_MODEL

    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return pick(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            if error.code in (429, 503) and attempt < 4:
                time.sleep(12 * (attempt + 1))
                continue
            raise RuntimeError(f"LLM HTTP {error.code}: {detail}") from None


def parse_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("у відповіді немає JSON-об'єкта")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("корінь JSON має бути об'єктом")
    return data


def positions(document, surface):
    if not surface:
        return []
    found = []
    start = 0
    while True:
        index = document.find(surface, start)
        if index < 0:
            break
        found.append(index)
        start = index + 1
    return found


def take_offset(document, surface, used, evidence=None):
    found = positions(document, surface)
    if not found:
        raise ValueError(f"текст {surface!r} не знайдено в документі")
    if evidence:
        if evidence not in document:
            raise ValueError("evidence не є підрядком документа")
        host = document.find(evidence)
        inner = [host + index for index in positions(evidence, surface)]
        if not inner:
            raise ValueError(f"{surface!r} немає в evidence")
        found = inner
    for index in found:
        span = (index, index + len(surface))
        if span not in used:
            used.add(span)
            return index
    return found[0]


def validate(data, document):
    mentions = data.get("mentions")
    relations = data.get("relations")
    if not isinstance(mentions, list) or not isinstance(relations, list):
        raise ValueError("потрібні списки mentions і relations")
    used = set()
    entities = []
    for item in mentions:
        type_ = item.get("type")
        surface = item.get("text")
        if type_ not in ENTITY_TYPES:
            raise ValueError(f"тип сутності поза словником: {type_}")
        start = take_offset(document, surface, used)
        entities.append(
            {
                "kind": "entity",
                "type": type_,
                "start": start,
                "end": start + len(surface),
                "text": surface,
            }
        )
    converted = []
    for item in relations:
        type_ = item.get("type")
        subject = item.get("subject")
        obj = item.get("object")
        evidence = item.get("evidence")
        if type_ not in RELATION_TYPES:
            raise ValueError(f"тип відношення поза словником: {type_}")
        if not isinstance(evidence, str):
            raise ValueError("у відношення немає evidence")
        subject_start = take_offset(document, subject, used, evidence)
        object_start = take_offset(document, obj, used, evidence)
        host = document.find(evidence)
        converted.append(
            {
                "kind": "relation",
                "type": type_,
                "start": host,
                "end": host + len(evidence),
                "text": evidence,
                "subject": subject,
                "object": obj,
                "subject_start": subject_start,
                "object_start": object_start,
            }
        )
    return entities + converted


def self_test():
    """Дві навмисні помилки, потім придатний JSON. API не викликається."""
    document = "Сплачено 10.00 грн контрагенту ТОВ «Уклон»."
    bad = ["не json", '{"mentions":[{"type":"Bank","text":"Уклон"}],"relations":[]}']
    good = {
        "mentions": [
            {"type": "Amount", "text": "10.00"},
            {"type": "Currency", "text": "грн"},
            {"type": "Counterparty", "text": "ТОВ «Уклон»"},
        ],
        "relations": [
            {
                "type": "paidTo",
                "subject": "10.00",
                "object": "ТОВ «Уклон»",
                "evidence": document,
            }
        ],
    }
    errors = []
    for raw in bad:
        try:
            parse_json(raw)
            validate(parse_json(raw), document)
        except (ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
    rows = validate(good, document)
    if len(errors) < 2 or len(rows) != 4:
        raise SystemExit(f"self-test не показав два повтори: {errors}")
    print(f"self-test: помилок до успіху {len(errors)}, прийнято тверджень {len(rows)}")


def main():
    if "--self-test" in sys.argv:
        self_test()
        return
    only = None
    if "--split" in sys.argv:
        only = sys.argv[sys.argv.index("--split") + 1]
    template = (ROOT / "prompts" / "extract_v1.md").read_text(encoding="utf-8")
    split_of = {}
    with (ROOT / "data" / "gold.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            split_of[row["doc_id"]] = row["split"]
    cache = load_cache()
    documents = sorted((ROOT / "data" / "docs").glob("d*.txt"))
    predictions = []
    tokens_in = 0
    tokens_out = 0
    model_name = None
    for path in documents:
        doc_id = path.stem
        if only and split_of.get(doc_id) != only:
            continue
        document = path.read_text(encoding="utf-8")
        prompt = template.replace("{{DOC_ID}}", doc_id).replace("{{DOCUMENT}}", document)
        accepted = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            cached = key in cache
            if cached:
                raw = cache[key]["raw"]
                tin = cache[key]["tokens_in"]
                tout = cache[key]["tokens_out"]
                model_name = cache[key]["model"]
            else:
                raw, tin, tout, model_name = call_llm(prompt)
                row = {
                    "key": key,
                    "raw": raw,
                    "tokens_in": tin,
                    "tokens_out": tout,
                    "model": model_name,
                }
                cache[key] = row
                append_jsonl(ROOT / "llm_log" / "cache.jsonl", row)
            tokens_in += 0 if cached else tin
            tokens_out += 0 if cached else tout
            error = ""
            try:
                accepted = validate(parse_json(raw), document)
            except (ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
            append_jsonl(
                ROOT / "llm_log" / "extract.jsonl",
                {
                    "date": datetime.now(timezone.utc).isoformat(),
                    "doc_id": doc_id,
                    "attempt": attempt,
                    "model": model_name,
                    "temperature": TEMPERATURE,
                    "seed": SEED,
                    "prompt_version": PROMPT_VERSION,
                    "prompt": prompt,
                    "raw_output": raw,
                    "tokens_in": tin,
                    "tokens_out": tout,
                    "cached": cached,
                    "validation_error": error,
                    "human_decision": "pending",
                },
            )
            if accepted is not None:
                break
            prompt += (
                "\nПопередня відповідь не пройшла перевірку: "
                + error
                + "\nПоверни виправлений JSON. evidence має бути точним підрядком документа, тип — лише з закритого списку."
            )
        if accepted is None:
            print(f"{doc_id}: не прийнято після {MAX_ATTEMPTS} спроб")
            continue
        for row in accepted:
            row["doc_id"] = doc_id
            row["model"] = model_name
            row["prompt_version"] = PROMPT_VERSION
            row["confidence"] = 0.6
            row["id"] = f"{doc_id}-l{len(predictions)+1:04d}"
            predictions.append(row)
        print(f"{doc_id}: {len(accepted)}")
    with (ROOT / "data" / "pred_llm.jsonl").open("w", encoding="utf-8") as handle:
        for row in predictions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    usage = {
        "model": model_name,
        "prompt_version": PROMPT_VERSION,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "documents": len(documents) if not only else sum(1 for doc, split in split_of.items() if split == only),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "predictions": len(predictions),
    }
    (ROOT / "data" / "llm_usage.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"predictions={len(predictions)} tokens_in={tokens_in} tokens_out={tokens_out}")


if __name__ == "__main__":
    main()
