"""Чотири ранжири. Ознаки беруться з train-кліків і з тексту документа, не з test."""

import hashlib
import math
import re
from collections import Counter, defaultdict

RRF_K = 60
DIM = 64


def by_user(rows, split):
    grouped = defaultdict(list)
    for row in rows:
        if row["split"] == split:
            grouped[row["user"]].append(row["doc"])
    return grouped


def _trigrams(text):
    folded = re.sub(r"\s+", " ", text.casefold())
    return [folded[index : index + 3] for index in range(len(folded) - 2)]


def _vector(text):
    vector = [0.0] * DIM
    for gram in _trigrams(text):
        digest = hashlib.sha256(gram.encode("utf-8")).digest()
        sign = 1.0 if digest[1] & 1 else -1.0
        vector[digest[0] % DIM] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left, right):
    return sum(a * b for a, b in zip(left, right))


def _order(scores):
    return [item for item, _score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]


def recommend(docs, rows, user, role="analyst", verified_only=True):
    from reco.data import allowed

    train = by_user(rows, "train")
    history = train.get(user, [])
    profile = set()
    for doc_id in history:
        profile |= docs[doc_id]["entities"]
    candidates = [
        doc_id
        for doc_id, doc in docs.items()
        if doc_id not in set(history) and allowed(doc, role=role, verified_only=verified_only)
    ]
    popularity = Counter(row["doc"] for row in rows if row["split"] == "train")
    pop_scores = {doc_id: popularity[doc_id] for doc_id in candidates}
    graph_scores = {doc_id: len(profile & docs[doc_id]["entities"]) for doc_id in candidates}
    vectors = {doc_id: _vector(docs[doc_id]["text"]) for doc_id in docs}
    if history:
        centroid = [0.0] * DIM
        for doc_id in history:
            for index, value in enumerate(vectors[doc_id]):
                centroid[index] += value
        centroid = [value / len(history) for value in centroid]
    else:
        centroid = [0.0] * DIM
    knn_scores = {doc_id: _cosine(centroid, vectors[doc_id]) for doc_id in candidates}
    lists = {
        "popularity": _order(pop_scores),
        "graph": _order(graph_scores),
        "knn": _order(knn_scores),
    }
    fused = defaultdict(float)
    for ranking in lists.values():
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] += 1.0 / (RRF_K + rank)
    lists["hybrid"] = _order(fused)
    paths = {doc_id: sorted(profile & docs[doc_id]["entities"]) for doc_id in candidates}
    return {"lists": lists, "paths": paths, "profile": sorted(profile), "popularity": popularity}


def surface(entity):
    return entity.split(":", 1)[1].replace("«", "").replace("»", "").strip()


def path_sentence(doc_id, entities):
    if not entities:
        return f"{doc_id}: спільного вузла з історією користувача немає."
    names = [surface(entity) for entity in entities[:3]]
    quoted = ", ".join(f"«{name}»" for name in names)
    return f"{doc_id}: спільний вузол {quoted}."
