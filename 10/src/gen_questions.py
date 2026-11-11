import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.3
SEED = 42

PROMPT = """Ти допомагаєш створити золотий набір для оцінювання пошуку. Ось фрагмент документа
«{title}» (розділ «{section}»):

\"\"\"{text}\"\"\"

Склади два запити українською, на які цей фрагмент дає відповідь:
1. "keyword" — короткий пошуковий запит з ключових слів фрагмента (3–6 слів);
2. "paraphrase" — природне питання, сформульоване ІНШИМИ словами, ніж у фрагменті.
Для кожного вкажи "answer_quote" — ТОЧНУ цитату з фрагмента (5–15 слів, без змін), яка є відповіддю.
Поверни лише JSON: {{"keyword": "...", "paraphrase": "...", "answer_quote": "..."}}"""


def api_key():
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GROQ_API_KEY не задано")
    return key.strip().strip('"')


def call_llm(prompt):
    body = {"model": MODEL, "temperature": TEMPERATURE, "seed": SEED,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key()}",
                 "User-Agent": "lab10-gold/1.0"}, method="POST")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 4:
                raise
            time.sleep(5)


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def main():
    chunks = [json.loads(ln) for ln in (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    public = [c for c in chunks if c["sensitivity"] == "public" and len(c["text"].split()) >= 60]
    rng = random.Random(SEED)
    by_doc = {}
    for c in public:
        by_doc.setdefault(c["doc_id"], []).append(c)
    picked = [rng.choice(v) for v in by_doc.values()]
    out = []
    (ROOT / "llm_log").mkdir(exist_ok=True)
    log = open(ROOT / "llm_log" / "gen_questions.jsonl", "w", encoding="utf-8")
    for c in picked:
        prompt = PROMPT.format(title=c["title"], section=c["section"], text=c["text"])
        raw = call_llm(prompt)
        try:
            cand = json.loads(raw)
        except json.JSONDecodeError:
            cand = {}
        if isinstance(cand, list):
            merged = {}
            for item in cand:
                if isinstance(item, dict):
                    merged.update({k: v for k, v in item.items() if k not in merged})
            cand = merged
        quote_ok = bool(cand.get("answer_quote")) and norm(cand["answer_quote"]) in norm(c["text"])
        rec = {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "title": c["title"], **cand,
               "quote_found": quote_ok}
        out.append(rec)
        log.write(json.dumps({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "model": MODEL, "temperature": TEMPERATURE, "seed": SEED,
                              "prompt_version": "gen-v1", "chunk_id": c["chunk_id"], "prompt": prompt,
                              "raw_output": raw, "decision": "pending_review"}, ensure_ascii=False) + "\n")
        print(c["chunk_id"], "quote_ok" if quote_ok else "QUOTE NOT FOUND", "|", cand.get("paraphrase"))
        time.sleep(2)
    log.close()
    with open(ROOT / "eval" / "candidates.jsonl", "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("кандидатів:", len(out), "з точною цитатою:", sum(r["quote_found"] for r in out))


if __name__ == "__main__":
    main()
