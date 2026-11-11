import json
import re
from pathlib import Path

import docx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LABS = ROOT.parent.parent / "labs"
LAB9 = ROOT.parent / "9" / "docs"

SKIP_SECTIONS = {"див. також", "примітки", "джерела", "література", "посилання", "виноски",
                 "джерела та література", "додаткова література", "зовнішні посилання"}

INTERNAL = [
    (LABS / "лр-5.docx", "ЛР5: Семантична мережа фінансових операцій у CmapTools (звіт)", "2026-09-27", "internal"),
    (LABS / "лр-7.docx", "ЛР7: Формалізація предметної області (звіт)", "2026-10-04", "internal"),
    (LABS / "лр-8.docx", "ЛР8: RDF-сховище знань (звіт)", "2026-10-18", "internal"),
    (LABS / "слр-5.docx", "СР5: Концептуальна карта фінансових операцій", "2026-09-20", "internal"),
]
CONFIDENTIAL = [
    (LAB9 / "cypher_results.md", "Аналітика витрат і бюджетів (запити Cypher)", "2026-10-25"),
    (LAB9 / "gds_report.md", "Аналіз графа фінансових операцій (PageRank, Louvain)", "2026-10-25"),
]


def clean_line(s):
    s = s.replace("́", "")
    s = re.sub(r"\{\\displaystyle[^}]*\}", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) > 2 else ""


def wiki_sections(text):
    sections, title, paras, skip = [], "Вступ", [], False
    for line in text.split("\n"):
        m = re.match(r"^(=+)\s*(.+?)\s*=+$", line.strip())
        if m:
            if paras and not skip:
                sections.append((title, paras))
            title, paras = m.group(2), []
            level = len(m.group(1))
            if level <= 2:
                skip = title.lower() in SKIP_SECTIONS
            continue
        s = clean_line(line)
        if s:
            paras.append(s)
    if paras and not skip:
        sections.append((title, paras))
    return sections


def docx_sections(path):
    d = docx.Document(path)
    lines = [p.text for p in d.paragraphs]
    start = next(i for i, s in enumerate(lines) if s.startswith("Мета роботи"))
    sections, title, paras = [], "Мета та предметна область", []
    for p in d.paragraphs[start:]:
        s = clean_line(p.text)
        if not s or re.match(r"^(Рис\.|Таблиця)\s*\d", s):
            continue
        bold = p.runs and all(r.bold for r in p.runs if r.text.strip())
        if bold and len(s) < 90 and re.match(r"^(\d+\.|Висновок|Хід роботи|Запит)", s):
            if paras:
                sections.append((title, paras))
            title, paras = s.rstrip(":"), []
        else:
            paras.append(s)
    for t in d.tables:
        rows = [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
        paras.append("; ".join(r for r in rows if r.strip()))
    if paras:
        sections.append((title, paras))
    return sections


def md_sections(path):
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    sections, title, paras = [], "Вступ", []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+)$", line)
        if m:
            if paras:
                sections.append((title, paras))
            title, paras = m.group(1).strip(), []
            continue
        if re.match(r"^\|?\s*-{3}", line):
            continue
        s = clean_line(re.sub(r"[*`#]", "", line).replace("|", " "))
        if s:
            paras.append(s)
    if paras:
        sections.append((title, paras))
    return sections


def pack(paras, max_words=180):
    out, cur = [], []
    for p in paras:
        pieces = [p]
        if len(p.split()) > max_words:
            sents = re.split(r"(?<=[.!?])\s+", p)
            pieces, buf = [], []
            for s in sents:
                if buf and len(" ".join(buf + [s]).split()) > max_words:
                    pieces.append(" ".join(buf))
                    buf = []
                buf.append(s)
            if buf:
                pieces.append(" ".join(buf))
        for piece in pieces:
            if cur and len(" ".join(cur + [piece]).split()) > max_words:
                out.append(" ".join(cur))
                cur = []
            cur.append(piece)
    if cur:
        out.append(" ".join(cur))
    return out


def main():
    docs = []
    for i, f in enumerate(sorted(RAW.glob("wiki_*.json")), start=1):
        w = json.loads(f.read_text(encoding="utf-8"))
        docs.append({"doc_id": f"D{i:02d}", "title": w["title"], "type": "encyclopedia",
                     "date": w["date"], "sensitivity": "public", "source_url": w["source_url"],
                     "license": w["license"], "sections": wiki_sections(w["text"])})
    n = len(docs)
    for j, (path, title, date, sens) in enumerate(INTERNAL, start=n + 1):
        docs.append({"doc_id": f"D{j:02d}", "title": title, "type": "internal_report", "date": date,
                     "sensitivity": sens, "source_url": f"file:labs/{path.name}",
                     "license": "власний документ", "sections": docx_sections(path)})
    n = len(docs)
    for j, (path, title, date) in enumerate(CONFIDENTIAL, start=n + 1):
        docs.append({"doc_id": f"D{j:02d}", "title": title, "type": "analytics", "date": date,
                     "sensitivity": "confidential", "source_url": f"file:9/docs/{path.name}",
                     "license": "власний документ", "sections": md_sections(path)})

    with open(ROOT / "data" / "documents.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    chunks = []
    for d in docs:
        k = 0
        for sec, paras in d["sections"]:
            for text in pack(paras):
                if len(text.split()) < 15:
                    continue
                k += 1
                chunks.append({"chunk_id": f"{d['doc_id']}-{k:03d}", "doc_id": d["doc_id"],
                               "title": d["title"], "section": sec, "type": d["type"], "date": d["date"],
                               "sensitivity": d["sensitivity"], "source_url": d["source_url"], "text": text})
    with open(ROOT / "data" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    from collections import Counter
    print("документів:", len(docs), "фрагментів:", len(chunks))
    print("sensitivity:", Counter(c["sensitivity"] for c in chunks))
    print("слів у фрагменті (сер.):", round(sum(len(c["text"].split()) for c in chunks) / len(chunks), 1))
    for d in docs:
        print(d["doc_id"], d["type"], d["sensitivity"], sum(1 for c in chunks if c["doc_id"] == d["doc_id"]),
              d["title"])


if __name__ == "__main__":
    main()
