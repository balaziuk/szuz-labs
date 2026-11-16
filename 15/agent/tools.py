"""Три інструменти лише для читання. Записів у сховище тут немає."""

import csv
import re
from pathlib import Path

LABS = Path(__file__).resolve().parents[2]
CSV_DIR = LABS / "9" / "data"
DOCS_DIR = LABS / "13" / "data" / "docs"
CATALOG = LABS / "13" / "data" / "catalog.csv"
INBOX = Path(__file__).resolve().parents[1] / "data" / "inbox"

def _read_csv(name):
    with (CSV_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _catalog():
    if not CATALOG.exists():
        return {}
    with CATALOG.open(encoding="utf-8-sig", newline="") as handle:
        return {row["doc_id"]: row for row in csv.DictReader(handle)}


def registry_lookup(query, limit=5):
    """Пошук у реєстрі контрагентів, категорій, рахунків і ризиків."""
    needle = query.casefold()
    hits = []
    for row in _read_csv("counterparties.csv"):
        blob = f"{row['name']} {row['edrpou']} {row['type']}"
        score = _score(needle, blob)
        if score:
            hits.append((score, row["id"], f"{row['name']}, ЄДРПОУ {row['edrpou']}, тип {row['type']}"))
    for row in _read_csv("categories.csv"):
        blob = f"{row['name']} {row['kind']} {row.get('budgetLimit', '')}"
        score = _score(needle, blob)
        if score and any(stem in needle for stem in ("ліміт", "категор")):
            score += 2
        if score:
            limit_text = row["budgetLimit"] or "немає"
            hits.append((score, row["id"], f"Категорія {row['name']} ({row['kind']}), ліміт {limit_text}"))
    for row in _read_csv("accounts.csv"):
        blob = f"{row['accountNumber']} {row['type']} {row['currency']}"
        score = _score(needle, blob)
        if "рахунк" in needle:
            score += 1
        if score:
            hits.append((score, row["id"], f"Рахунок {row['accountNumber']}, {row['type']}, {row['currency']}, залишок {row['balance']}"))
    for row in _read_csv("risks.csv"):
        blob = f"{row['id']} {row['type']} {row['description']}"
        score = _score(needle, blob)
        if "ризик" in needle:
            score += 2
        if score:
            hits.append((score, row["id"], f"{row['id']}: {row['description']} (рівень {row['level']})"))
    hits.sort(key=lambda item: item[0], reverse=True)
    packed = [{"id": item_id, "quote": quote} for _score, item_id, quote in hits[:limit]]
    return {"tool": "registry_lookup", "query": query, "hits": packed}


def search_notes(query, role="analyst", limit=3):
    """Пошук у документах ЛР13 і у вхідній скриньці. Роль public не бачить note та inbox."""
    catalog = _catalog()
    tokens = _tokens(query)
    scored = []
    files = list(DOCS_DIR.glob("d*.txt")) if DOCS_DIR.exists() else []
    files.extend(INBOX.glob("*.txt"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        doc_id = path.stem
        kind = catalog.get(doc_id, {}).get("source_kind", "inbox")
        if role != "analyst" and kind in {"note", "inbox"}:
            continue
        folded = text.casefold()
        score = sum(1 for token in tokens if token[:5] in folded)
        if kind == "inbox" and score < 2:
            continue
        month = re.search(r"20\d{2}-\d{2}", query)
        if month and month.group(0) in text:
            score += 3
        elif "жовт" in query.casefold() and "2026-10" in text:
            score += 3
        if score <= 0:
            continue
        # Документи короткі, тому інструмент віддає текст цілком (до 400 символів).
        body = " ".join(line.strip() for line in text.splitlines() if line.strip())[:400]
        scored.append((score, {"id": doc_id, "quote": body, "sensitivity": kind}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return {"tool": "search_notes", "query": query, "role": role, "hits": [row for _score, row in scored[:limit]]}


TOPICS = {"rent": "оренд", "utilities": "комунал", "salary": "зарплат"}


def operations_query(month=None, topic=None, metric="list"):
    """Закритий фільтр операцій: місяць YYYY-MM, тема rent|utilities|salary, метрика list|rent_share.

    Вільного SQL немає, тому запит на зміну просто нема як передати.
    """
    if month is not None and not re.fullmatch(r"20\d{2}-\d{2}", str(month)):
        return {"tool": "operations_query", "error": "month має формат YYYY-MM", "hits": []}
    if topic not in (None, "", "all", *TOPICS):
        return {"tool": "operations_query", "error": "topic: rent, utilities, salary або all", "hits": []}
    if metric not in ("list", "rent_share"):
        return {"tool": "operations_query", "error": "metric: list або rent_share", "hits": []}
    args = {"month": month, "topic": topic, "metric": metric}
    rows = _read_csv("operations.csv")
    if metric == "rent_share":
        expenses = [row for row in rows if row["kind"] == "Expense"]
        rent = [row for row in expenses if "оренд" in row["description"]]
        total = sum(float(row["amount"]) for row in expenses)
        part = sum(float(row["amount"]) for row in rent)
        share = part / total if total else 0
        quote = f"Частка оренди серед витрат {share:.1%} ({part:.0f} із {total:.0f} грн)"
        return {"tool": "operations_query", "args": args, "hits": [{"id": "operations.csv", "quote": quote}]}
    stem = TOPICS.get(topic or "")
    chosen = [
        row
        for row in rows
        if (not month or row["date"].startswith(month)) and (not stem or stem in row["description"])
    ]
    hits = [
        {
            "id": row["id"],
            "quote": f"{row['id']} {row['date']} {row['kind']} {row['amount']} {row['currency']}: {row['description']}",
        }
        for row in chosen[:8]
    ]
    return {"tool": "operations_query", "args": args, "hits": hits}


# JSON-схеми, які бачить модель і які оголошує MCP-сервер.
TOOL_SPECS = [
    {
        "name": "registry_lookup",
        "description": "Реєстр хаба: контрагенти (назва, ЄДРПОУ, тип), категорії з лімітами, рахунки, ризики. Лише читання.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200, "description": "ключові слова, напр. «Роботодавець ЄДРПОУ»"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_notes",
        "description": "Повнотекстовий пошук у документах хаба (виписки, картки, політики, ризики, нотатки). Лише читання. Права залежать від ролі сесії.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
        },
    },
    {
        "name": "operations_query",
        "description": "Операції з виписки за закритим фільтром. Лише читання, вільного SQL немає.",
        "parameters": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "pattern": "^20[0-9]{2}-[0-9]{2}$"},
                "topic": {"type": "string", "enum": ["rent", "utilities", "salary", "all"]},
                "metric": {"type": "string", "enum": ["list", "rent_share"], "default": "list"},
            },
        },
    },
]
TRUSTED_TOOLS = {spec["name"] for spec in TOOL_SPECS}


def call_tool(name, arguments, role="analyst"):
    """Роль приходить із сесії, а не від моделі."""
    arguments = arguments or {}
    if name == "registry_lookup":
        return registry_lookup(str(arguments.get("query", ""))[:200])
    if name == "search_notes":
        return search_notes(str(arguments.get("query", ""))[:200], role=role)
    if name == "operations_query":
        return operations_query(arguments.get("month"), arguments.get("topic"), arguments.get("metric") or "list")
    return {"tool": name, "error": "інструмент не дозволений", "hits": []}


def _tokens(text):
    return [token for token in re.findall(r"[0-9a-zа-яіїєґ']{4,}", text.casefold())]


def _score(query, blob):
    folded = blob.casefold()
    return sum(1 for token in _tokens(query) if token[:5] in folded)


def _snippet(text, tokens):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    best = ""
    best_score = -1
    for line in lines:
        folded = line.casefold()
        score = sum(len(token) for token in tokens if not token.isdigit() and token[:5] in folded)
        if score <= 0:
            continue
        if any(character.isdigit() for character in line):
            score += 1
        if score > best_score:
            best, best_score = line, score
    if best:
        return best[:240]
    return (lines[0][:240] if lines else "")
