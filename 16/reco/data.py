"""Синтетичні взаємодії. Seed 42. Клік не може бути раніший за дату документа."""

import csv
import json
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABS = Path(os.environ.get("SZUZ_LABS", ROOT.parent))
SEED = 42
SPLIT = date(2026, 8, 1)
END = date(2026, 10, 20)
FRESH_FROM = date(2026, 2, 1)
CONTENT_TYPES = {"Counterparty", "Category", "Risk", "Account"}
N_USERS = 60


def load_docs():
    catalog = LABS / "13" / "data" / "catalog.csv"
    docs = {}
    with catalog.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            docs[row["doc_id"]] = {
                "id": row["doc_id"],
                "title": row["title"],
                "kind": row["source_kind"],
                "date": date.fromisoformat(row["date"]),
                "verified": row["source_kind"] != "note",
                "sensitivity": "internal" if row["source_kind"] in {"note", "inbox"} else "public",
            }
    gold = LABS / "13" / "data" / "gold.jsonl"
    entities = {doc_id: set() for doc_id in docs}
    with gold.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] != "entity" or row["type"] not in CONTENT_TYPES:
                continue
            entities[row["doc_id"]].add(f"{row['type']}:{row['text'].casefold()}")
    for doc_id, doc in docs.items():
        doc["entities"] = entities[doc_id]
        text = (LABS / "13" / "data" / "docs" / f"{doc_id}.txt").read_text(encoding="utf-8")
        doc["text"] = text
    return docs


def allowed(doc, role="analyst", fresh_from=FRESH_FROM, verified_only=True):
    if verified_only and not doc["verified"]:
        return False
    if doc["date"] < fresh_from:
        return False
    if role != "analyst" and doc["sensitivity"] != "public":
        return False
    return True


def build_interactions(docs, users=N_USERS):
    rng = random.Random(SEED)
    frequent = {}
    for doc in docs.values():
        if not doc["verified"]:
            continue
        for entity in doc["entities"]:
            frequent.setdefault(entity, set()).add(doc["id"])
    choices = sorted(entity for entity, owners in frequent.items() if len(owners) >= 2)
    rows = []
    for index in range(1, users + 1):
        user = f"u{index:02d}"
        interests = rng.sample(choices, 2)
        matching = [doc for doc in docs.values() if doc["verified"] and doc["entities"] & set(interests)]
        train_pool = [doc for doc in matching if doc["date"] < SPLIT]
        test_pool = [doc for doc in matching if doc["date"] <= END]
        if len(train_pool) < 2:
            train_pool = [doc for doc in docs.values() if doc["verified"] and doc["date"] < SPLIT]
        rng.shuffle(train_pool)
        rng.shuffle(test_pool)
        chosen = {}
        for doc in train_pool[:3]:
            start = doc["date"]
            finish = SPLIT - timedelta(days=1)
            if start <= finish:
                chosen[doc["id"]] = _between(rng, start, finish)
        for doc in test_pool:
            if doc["id"] in chosen:
                continue
            start = max(doc["date"], SPLIT)
            if start <= END and len([item for item in chosen.values() if item >= SPLIT]) < 2:
                chosen[doc["id"]] = _between(rng, start, END)
            if len([item for item in chosen.values() if item >= SPLIT]) >= 2:
                break
        for doc_id, when in chosen.items():
            rows.append(
                {
                    "user": user,
                    "doc": doc_id,
                    "date": when.isoformat(),
                    "split": "train" if when < SPLIT else "test",
                    "interests": "|".join(interests),
                }
            )
    return rows


def save(docs, rows):
    data = ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)
    with (data / "interactions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user", "doc", "date", "split", "interests"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "seed": SEED,
        "users": N_USERS,
        "rows": len(rows),
        "split": "date < 2026-08-01 train; date >= 2026-08-01 test",
        "fresh_from": FRESH_FROM.isoformat(),
        "note": "Користувачі синтетичні. Клік не раніше дати документа і не пізніше 2026-10-20.",
    }
    (data / "interactions_meta.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _between(rng, start, finish):
    span = (finish - start).days
    return start + timedelta(days=rng.randrange(span + 1))


def load_rows():
    rows = []
    with (ROOT / "data" / "interactions.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row["date"] = date.fromisoformat(row["date"])
            rows.append(row)
    return rows
