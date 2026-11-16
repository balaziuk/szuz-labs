"""Метод А: словник ЛР9, регулярні вирази і spaCy (токенізація + EntityRuler).

На dev статистичний NER не збігався з типами схеми, тому в предикт він не пишеться.
Вихід: data/pred_rules.jsonl
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schema import gazetteer

PROMPT_VERSION = "rules_v1"
PRIORITY = {"Account": 0, "Edrpou": 1, "Period": 2, "Amount": 3, "Risk": 4, "Counterparty": 5, "Category": 6, "Currency": 7}


class _Token:
    def __init__(self, text):
        self.text = text


class _Doc:
    def __init__(self, text):
        self.text = text
        self.ents = []

    def __iter__(self):
        return iter(_Token(piece) for piece in self.text.split())


def load_nlp():
    """spaCy, якщо імпорт не заблокований; інакше той самий словник фраз без моделі."""
    try:
        import spacy

        try:
            nlp = spacy.load("uk_core_news_sm")
            model_name = "uk_core_news_sm+entity_ruler"
        except OSError:
            nlp = spacy.blank("uk")
            model_name = "spacy.blank(uk)+entity_ruler"
        if "entity_ruler" not in nlp.pipe_names:
            nlp.add_pipe(
                "entity_ruler",
                before="ner" if "ner" in nlp.pipe_names else None,
            )
        ruler = nlp.get_pipe("entity_ruler")
        patterns = []
        for phrase, type_, _ident in gazetteer():
            patterns.append({"label": type_, "pattern": [{"ORTH": token} for token in phrase.split(" ")]})
        ruler.add_patterns(patterns)
        return nlp, model_name
    except (ImportError, OSError) as error:
        print(f"spaCy недоступний ({error.__class__.__name__}: {error}). Працює словник і регулярні вирази.")
        return None, "regex+gazetteer"


def overlaps(spans, start, end):
    return any(not (end <= left or start >= right) for left, right, _type in spans)


def add_span(spans, start, end, type_):
    if start < 0 or end <= start or overlaps(spans, start, end):
        return
    spans.append((start, end, type_))


def find_entities(text):
    spans = []
    for match in re.finditer(r"UA\d{9,14}", text):
        add_span(spans, match.start(), match.end(), "Account")
    offset = 0
    for line in text.split("\n"):
        if "єдрпоу" in line.lower():
            for match in re.finditer(r"(?<!\d)\d{8}(?!\d)", line):
                add_span(spans, offset + match.start(), offset + match.end(), "Edrpou")
        offset += len(line) + 1
    for match in re.finditer(r"(?<!\d)\d{4}-\d{2}(?!\d)", text):
        add_span(spans, match.start(), match.end(), "Period")
    for match in re.finditer(r"(?<!\d)\d+\.\d{2}(?!\d)", text):
        add_span(spans, match.start(), match.end(), "Amount")
    for phrase, type_, _ident in gazetteer():
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
            add_span(spans, match.start(), match.end(), type_)
    for match in re.finditer(r"(?<!\w)(?:UAH|USD|грн)(?!\w)", text):
        add_span(spans, match.start(), match.end(), "Currency")
    spans.sort(key=lambda item: (item[0], PRIORITY.get(item[2], 9)))
    return spans


def line_bounds(text, pos):
    begin = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return begin, end


def nearest(anchor, candidates):
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item["start"] - anchor["start"]))


def relations_for_line(line_start, line_text, entities):
    local = [row for row in entities if line_start <= row["start"] < line_start + len(line_text)]
    amounts = [row for row in local if row["type"] == "Amount"]
    parties = [row for row in local if row["type"] == "Counterparty"]
    categories = [row for row in local if row["type"] == "Category"]
    periods = [row for row in local if row["type"] == "Period"]
    codes = [row for row in local if row["type"] == "Edrpou"]
    risks = [row for row in local if row["type"] == "Risk"]
    low = line_text.lower()
    found = []

    def emit(type_, left, right):
        found.append((type_, left, right))

    if any(word in low for word in ("сплачено", "оплачено", "списано")):
        for amount in amounts:
            party = nearest(amount, parties)
            if party:
                emit("paidTo", amount, party)
    if any(word in low for word in ("зараховано", "отримано", "надійшло")):
        for amount in amounts:
            party = nearest(amount, parties)
            if party:
                emit("receivedFrom", amount, party)
    if "ліміт" in low:
        for category in categories:
            amount = nearest(category, amounts)
            if amount:
                emit("hasBudgetLimit", category, amount)
    elif "категорі" in low:
        for amount in amounts:
            category = nearest(amount, categories)
            if category:
                emit("hasCategory", amount, category)
    if "єдрпоу" in low:
        for party in parties:
            code = nearest(party, codes)
            if code:
                emit("identifiedBy", party, code)
    if "період" in low and "ліміт" not in low:
        anchors = amounts or risks
        for anchor in anchors:
            period = nearest(anchor, periods)
            if period:
                emit("inPeriod", anchor, period)
    if "стосується" in low or "зачеплена" in low:
        for risk in risks:
            category = nearest(risk, categories)
            if category:
                emit("concerns", risk, category)
    unique = []
    seen = set()
    for type_, left, right in found:
        key = (type_, left["start"], right["start"])
        if key in seen:
            continue
        seen.add(key)
        unique.append((type_, left, right))
    return unique


def extract_document(doc_id, text, model_name, nlp):
    spacy_doc = nlp(text) if nlp is not None else _Doc(text)
    ner_labels = {}
    for ent in spacy_doc.ents:
        ner_labels[ent.label_] = ner_labels.get(ent.label_, 0) + 1
    raw = find_entities(text)
    entities = [
        {
            "doc_id": doc_id,
            "kind": "entity",
            "type": type_,
            "start": start,
            "end": end,
            "text": text[start:end],
            "model": model_name,
            "prompt_version": PROMPT_VERSION,
            "confidence": 0.95 if type_ in {"Counterparty", "Category", "Risk"} else 0.99,
        }
        for start, end, type_ in raw
    ]
    relations = []
    offset = 0
    for line in text.split("\n"):
        for type_, left, right in relations_for_line(offset, line, entities):
            relations.append(
                {
                    "doc_id": doc_id,
                    "kind": "relation",
                    "type": type_,
                    "start": offset,
                    "end": offset + len(line),
                    "text": line,
                    "subject": left["text"],
                    "object": right["text"],
                    "subject_start": left["start"],
                    "object_start": right["start"],
                    "model": model_name,
                    "prompt_version": PROMPT_VERSION,
                    "confidence": 0.9,
                }
            )
        offset += len(line) + 1
    return entities + relations, ner_labels


def main():
    nlp, model_name = load_nlp()
    catalog = {}
    docs_dir = ROOT / "data" / "docs"
    for path in sorted(docs_dir.glob("d*.txt")):
        catalog[path.stem] = path.read_text(encoding="utf-8")
    rows = []
    ner_total = {}
    for doc_id, text in catalog.items():
        extracted, ner_labels = extract_document(doc_id, text, model_name, nlp)
        for label, count in ner_labels.items():
            ner_total[label] = ner_total.get(label, 0) + count
        for row in extracted:
            row["id"] = f"{doc_id}-p{len(rows)+1:04d}"
            rows.append(row)
    destination = ROOT / "data" / "pred_rules.jsonl"
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"rules={len(rows)} model={model_name} ner={ner_total}")


if __name__ == "__main__":
    main()
