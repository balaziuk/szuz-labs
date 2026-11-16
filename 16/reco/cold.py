"""Холодний старт: новий користувач зі заявленим інтересом і новий документ."""

from collections import Counter

from reco.data import allowed
from reco.recommend import recommend


def new_user(docs, rows):
    """Історії користувача немає. Список — документи зі заявленим вузлом, популярність рахується без його кліків."""
    scores = []
    seen = set()
    for row in rows:
        if row["user"] in seen or row["split"] != "test":
            continue
        seen.add(row["user"])
        interest = row["interests"].split("|")[0]
        popularity = Counter(
            item["doc"]
            for item in rows
            if item["split"] == "train" and item["user"] != row["user"]
        )
        ranking = [
            doc_id
            for doc_id, doc in docs.items()
            if allowed(doc) and interest in doc["entities"]
        ]
        ranking.sort(key=lambda doc_id: (-popularity[doc_id], doc_id))
        relevant = {
            item["doc"]
            for item in rows
            if item["user"] == row["user"]
            and item["split"] == "test"
            and allowed(docs[item["doc"]])
            and interest in docs[item["doc"]]["entities"]
        }
        if not relevant:
            continue
        hits = sum(1 for doc_id in ranking[:5] if doc_id in relevant)
        scores.append(hits / 5)
        if len(scores) == 30:
            break
    mean = sum(scores) / len(scores) if scores else 0.0
    return {
        "users": len(scores),
        "p5": mean,
        "interest_source": "перший вузол із поля interests; історію користувача не використано",
    }


def new_item(docs, rows, doc_id="d19"):
    """d19 датований 2026-10-01, тому в train його немає. Дивимось, чи граф ставить його в топ-5 тим, хто вже читав спільний вузол."""
    users = sorted({row["user"] for row in rows if row["split"] == "train"})
    hits = 0
    eligible = 0
    for user in users:
        result = recommend(docs, rows, user)
        path = result["paths"].get(doc_id) or []
        if not path:
            continue
        eligible += 1
        if doc_id in result["lists"]["graph"][:5]:
            hits += 1
    return {
        "item": doc_id,
        "users_with_shared_node": eligible,
        "in_top5": hits,
        "rate": hits / eligible if eligible else 0.0,
    }
