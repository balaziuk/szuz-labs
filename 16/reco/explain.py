"""Пояснення зі спільних вузлів шляху. LLM лише перефразовує речення шляху; перевірка відкидає сутність поза шляхом.

Перефразування: Groq (ключ GROQ_API_KEY або GEMINI_API_KEY з префіксом gsk_), модель qwen/qwen3.8-27b,
temperature 0, seed 42, промпт explain_v1. Кожен виклик пишеться в llm_log/reco.jsonl, відповідь кешується
в llm_log/explain_cache.jsonl. Без ключа й кешу перефразування немає, показується речення шляху.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from reco.recommend import path_sentence, recommend, surface

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "llm_log" / "reco.jsonl"
CACHE = ROOT / "llm_log" / "explain_cache.jsonl"
MODEL = os.environ.get("LAB16_EXPLAIN_MODEL", "qwen/qwen3.8-27b")
PROMPT_VERSION = "explain_v1"
TEMPERATURE = 0.0
SEED = 42
QUOTE = re.compile(r"«([^»]+)»")

PROMPT = """Перефразуй службове пояснення рекомендації одним природним реченням українською для користувача фінансового хабу.
Документ: {doc_id} («{title}»).
Службове пояснення: {sentence}
Дозволені назви сутностей (лише ці, дослівно, кожну в лапках «»): {allowed}.
Не додавай інших назв організацій, категорій, рахунків, ризиків, сум чи дат. Не вигадуй, чому документ корисний, понад спільні сутності.
Поверни лише JSON: {{"text": "речення"}}"""


def check(sentence, path):
    """Базова перевірка: кожна назва в «» є поверхневою формою вузла шляху."""
    allowed = {surface(entity).casefold() for entity in path}
    quoted = QUOTE.findall(sentence)
    if not path and quoted:
        return False
    return all(quote.casefold().strip() in allowed for quote in quoted)


def foreign_entities(sentence, path, docs):
    """Сутності каталогу, які згадані в реченні, але не входять у шлях (навіть без лапок)."""
    inside = {surface(entity).casefold() for entity in path}
    known = {surface(entity).casefold() for doc in docs.values() for entity in doc["entities"]}
    folded = sentence.casefold().replace("«", "").replace("»", "")
    found = []
    for name in sorted(known - inside):
        if len(name) < 4 or any(name in own for own in inside):
            continue
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", folded):
            found.append(name)
    return found


def strict_check(sentence, path, docs):
    return check(sentence, path) and not foreign_entities(sentence, path, docs)


def _key():
    return (os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip().strip('"')


def _cache():
    if not CACHE.exists():
        return {}
    return {row["key"]: row for row in (json.loads(x) for x in CACHE.read_text(encoding="utf-8").splitlines() if x.strip())}


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _call(prompt):
    body = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {_key()}", "User-Agent": "lab16-explain/1.0"}
    for attempt in range(8):
        request = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            usage = data.get("usage") or {}
            time.sleep(2)
            return data["choices"][0]["message"]["content"], usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 503) and attempt < 7:
                retry = error.headers.get("retry-after") if error.headers else None
                time.sleep(min(float(retry) + 2 if retry else 15 * (attempt + 1), 600))
                continue
            raise RuntimeError(f"LLM HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from None
    raise RuntimeError("вичерпано повтори")


def paraphrase(doc_id, path, sentence, docs):
    """Повертає {"text", "ok", "foreign", "cached"} або None, якщо моделі немає."""
    allowed = ", ".join(f"«{surface(entity)}»" for entity in path[:3])
    prompt = PROMPT.format(doc_id=doc_id, title=docs[doc_id]["title"], sentence=sentence, allowed=allowed)
    key = hashlib.sha256(json.dumps([MODEL, PROMPT_VERSION, prompt], ensure_ascii=False).encode("utf-8")).hexdigest()
    cache = _cache()
    if key in cache:
        row, cached = cache[key], True
    elif _key().startswith("gsk_"):
        raw, tokens_in, tokens_out = _call(prompt)
        row, cached = {"key": key, "raw": raw, "tokens_in": tokens_in, "tokens_out": tokens_out}, False
        _append(CACHE, row)
    else:
        return None
    try:
        text = json.loads(row["raw"][row["raw"].find("{"): row["raw"].rfind("}") + 1]).get("text", "").strip()
    except (ValueError, json.JSONDecodeError):
        text = ""
    # Назва самого рекомендованого документа — не сторонній вузол (перевірка v2; v1 її відкидала).
    body = re.sub(rf"«?{re.escape(docs[doc_id]['title'])}»?", "", text, flags=re.I) if text else ""
    foreign = foreign_entities(body, path[:3], docs) if body else []
    ok = bool(text) and check(body, path[:3]) and not foreign
    if not cached:
        _append(LOG, {
            "date": datetime.now(timezone.utc).isoformat(),
            "doc": doc_id,
            "model": MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "prompt_version": PROMPT_VERSION,
            "prompt": prompt,
            "raw_output": row["raw"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "auto_check": "pass" if ok else "fail",
            "checker": "v2",
            "foreign_entities": foreign,
            "human_decision": None,
        })
    return {"text": text, "ok": ok, "foreign": foreign, "cached": cached}


def examples(docs, rows, user, limit=5):
    result = recommend(docs, rows, user)
    chosen = []
    for doc_id in result["lists"]["graph"]:
        path = result["paths"][doc_id]
        if not path:
            continue
        sentence = path_sentence(doc_id, path)
        llm = paraphrase(doc_id, path, sentence, docs)
        chosen.append(
            {
                "user": user,
                "doc": doc_id,
                "path": path,
                "sentence": sentence,
                "ok": check(sentence, path),
                "llm": llm,
                "shown": llm["text"] if llm and llm["ok"] else sentence,
            }
        )
        if len(chosen) == limit:
            break
    return chosen


def paraphrase_eval(docs, rows, users, limit=5):
    """Частка LLM-пояснень, що спираються лише на шлях, на топ-5 графа кількох користувачів."""
    items = []
    for user in users:
        items.extend(examples(docs, rows, user, limit=limit))
    with_llm = [item for item in items if item["llm"]]
    return {
        "users": len(users),
        "explanations": len(items),
        "llm_explanations": len(with_llm),
        "llm_ok": sum(item["llm"]["ok"] for item in with_llm),
        "llm_rate": (sum(item["llm"]["ok"] for item in with_llm) / len(with_llm)) if with_llm else None,
        "failed": [{"user": i["user"], "doc": i["doc"], "text": i["llm"]["text"], "foreign": i["llm"]["foreign"]} for i in with_llm if not i["llm"]["ok"]],
    }


def control_failure(example):
    sentence = example["sentence"] + " Також згадано «неіснуючий-вузол»."
    return {"sentence": sentence, "ok": check(sentence, example["path"])}


def control_foreign(example, docs):
    """Контроль суворої перевірки: сутність каталогу поза шляхом без лапок."""
    inside = {surface(entity).casefold() for entity in example["path"]}
    other = next(surface(e) for d in sorted(docs) for e in sorted(docs[d]["entities"])
                 if surface(e).casefold() not in inside and len(surface(e)) >= 6 and not any(surface(e).casefold() in own for own in inside))
    sentence = example["sentence"] + f" Схоже на документи про {other}."
    return {"sentence": sentence, "ok": strict_check(sentence, example["path"], docs), "planted": other}
