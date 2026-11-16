"""Захисти агента. Політика v1 їх не вмикає, щоб було з чим порівняти."""

import re

from agent.tools import TRUSTED_TOOLS

INJECTION = re.compile(
    r"(ігнору\w*|ignore\s+(all|previous|the)|системн\w*\s+промпт|system\s+prompt|інструкці\w*\s+агент\w*"
    r"|службов\w*\s+маркер|kanarka|exfiltrat\w*|you\s+are\s+now|ти\s+тепер|забудь\s+(усі|всі|попередні)"
    r"|developer\s+mode|режим\s+(адміністратора|розробника)|виведи\s+(всі|усі)\s+(внутрішні|приватні))",
    re.IGNORECASE,
)
WRITE = re.compile(
    r"\b(delete|drop|update|insert|truncate|alter|видал\w*|стер\w*|знищ\w*|очист\w*|запиш\w*|перезапиш\w*|зміни\s+суму)\b",
    re.IGNORECASE,
)
SECRET = re.compile(r"(парол\w*|password|api[\s_-]?key|токен\w*|ключ\w*\s+api)", re.IGNORECASE)
NUMBER = re.compile(r"(?<!\d)\d{1,3}(?:[ \u00a0\u202f]\d{3}(?!\d))+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")

MAX_STEPS = 4
MAX_TOKENS = 12000
MAX_CHARS = 6000


def looks_like_injection(text):
    return bool(INJECTION.search(text or ""))


def looks_like_write(text):
    return bool(WRITE.search(text or ""))


def asks_for_secret(text):
    return bool(SECRET.search(text or ""))


def pin_tools(specs):
    """Лишає тільки інструменти з білого списку; опис з ін'єкцією теж відкидається."""
    kept, rejected = [], []
    for spec in specs:
        if spec["name"] not in TRUSTED_TOOLS:
            rejected.append({"tool": spec["name"], "reason": "немає в білому списку"})
        elif looks_like_injection(spec.get("description", "")):
            rejected.append({"tool": spec["name"], "reason": "опис схожий на ін'єкцію"})
        else:
            kept.append(spec)
    return kept, rejected


def allow_tool(name):
    if name not in TRUSTED_TOOLS:
        return False, "інструмент поза білим списком"
    return True, ""


def _sentences(text):
    return [part for part in re.split(r"(?<=[.!?])\s+", text) if part]


def strip_injection(observation):
    """Вирізає речення з інструкціями всередині даних. Повертає (очищене, скільки вирізано)."""
    removed = 0
    hits = []
    for hit in observation.get("hits", []):
        quote = hit.get("quote", "")
        kept = []
        for sentence in _sentences(quote):
            if looks_like_injection(sentence):
                removed += 1
            else:
                kept.append(sentence)
        if kept:
            hits.append({**hit, "quote": " ".join(kept)})
    return {**observation, "hits": hits}, removed


def _numbers(text):
    found = set()
    for raw in NUMBER.findall(text or ""):
        digits = re.sub(r"[ \u00a0\u202f]", "", raw).replace(",", ".")
        if "." in digits:
            digits = digits.rstrip("0").rstrip(".")
        if len(digits.replace(".", "")) >= 3:
            found.add(digits)
    return found


def verify_answer(answer, citations, observations, canary):
    """Перевірка цитат перед відповіддю: кожне джерело є серед результатів інструментів,
    кожне число з відповіді є в процитованих фрагментах, службового маркера немає."""
    if canary and canary in (answer or ""):
        return {"ok": False, "reason": "у відповіді службовий маркер"}
    if (answer or "").startswith(("Не знаю", "Не виконую", "Запис і видалення", "Не можу")):
        return {"ok": True, "reason": "відмова"}
    quotes = {}
    for observation in observations:
        for hit in observation.get("hits", []):
            quotes.setdefault(hit.get("id"), []).append(hit.get("quote", ""))
    if not citations:
        return {"ok": False, "reason": "немає жодної цитати"}
    missing = [item for item in citations if item not in quotes]
    if missing:
        return {"ok": False, "reason": f"джерела не з інструментів: {missing}"}
    cited_text = " ".join(" ".join(quotes[item]) for item in citations)
    unsupported = sorted(_numbers(answer) - _numbers(cited_text) - _numbers(" ".join(citations)))
    if unsupported:
        return {"ok": False, "reason": f"числа без підтвердження: {unsupported}"}
    return {"ok": True, "reason": "цитати з інструментів"}
