import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB10 = ROOT.parent / "10"
lab10_src = str(LAB10 / "src")
if lab10_src not in sys.path:
    sys.path.append(lab10_src)

from evaluate import abstains
from hybrid import HybridSearcher
from search_lib import load_jsonl

CITE = re.compile(r"\[\s*([A-Za-z][A-Za-z0-9_\-]+)\s*\]")
REJECTED = "Не знаю: відповідь відхилено, бо вона не підкріплена цитатами з контексту."


def load_searcher():
    chunks = load_jsonl(LAB10 / "data" / "chunks_fixed.jsonl")
    return HybridSearcher(chunks), {c["chunk_id"]: c for c in chunks}


def filters_for(role):
    if role == "public":
        return {"sensitivity": ["public"]}
    return None


def render(chunks, graph_text):
    blocks, allowed = [], set()
    for c in chunks:
        allowed.add(c["chunk_id"])
        blocks.append(
            f"[{c['chunk_id']}] type={c['type']} sensitivity={c['sensitivity']} date={c['date']}\n{c['text']}"
        )
    if graph_text:
        blocks.append("Підграф:\n" + graph_text)
    return "\n\n".join(blocks), allowed


def cited_ids(answer):
    text = (answer or "").replace("\u3010", "[").replace("\u3011", "]")
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014"):
        text = text.replace(dash, "-")
    for invisible in ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
        text = text.replace(invisible, "")
    return CITE.findall(text)


def check_citations(answer, allowed):
    ids = cited_ids(answer)
    invalid = [i for i in ids if i not in allowed]
    return ids, invalid


def verdict(raw, allowed):
    ids, invalid = check_citations(raw, allowed)
    rejected = bool(invalid) or (not ids and not abstains(raw))
    return (REJECTED if rejected else raw), ids, invalid, rejected


def cached_call(prompt, judge=False):
    from llm import call_llm

    path = ROOT / "llm_log" / "cache.jsonl"
    path.parent.mkdir(exist_ok=True)
    key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row["key"] == key:
                    return row["raw"], row["tin"], row["tout"], row["model"], row["latency_ms"], True
    t0 = time.perf_counter()
    raw, tin, tout, model = call_llm(prompt, judge=judge)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "raw": raw, "tin": tin, "tout": tout, "model": model,
                            "latency_ms": latency_ms}, ensure_ascii=False) + "\n")
    return raw, tin, tout, model, latency_ms, False


def ask(searcher, question, template, role="analyst", k=5, graph_text="", graph_ids=None, extra=None):
    t0 = time.perf_counter()
    hits = searcher.search(question, mode="hybrid_rerank", k=k, filters=filters_for(role))
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
    chunks = list(extra or []) + list(hits)
    context, allowed = render(chunks, graph_text)
    allowed |= set(graph_ids or [])
    prompt = template.format(context=context, question=question)
    raw, tokens_in, tokens_out, model, llm_ms, cached = cached_call(prompt)
    answer, ids, invalid, rejected = verdict(raw, allowed)
    return {
        "question": question,
        "answer": answer,
        "raw_answer": raw,
        "rejected": rejected,
        "graph_nodes": sorted(graph_ids or []),
        "sources": [c["chunk_id"] for c in chunks],
        "source_meta": [{"id": c["chunk_id"], "sensitivity": c.get("sensitivity"), "type": c.get("type")} for c in chunks],
        "cited": ids,
        "invalid_citations": invalid,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": round(retrieval_ms + llm_ms, 1),
        "retrieval_ms": retrieval_ms,
        "llm_ms": llm_ms,
        "cached": cached,
        "model": model,
        "prompt": prompt,
        "context_chunks": chunks,
        "graph_text": graph_text,
    }


def ask_with_graph(searcher, graph, question, template, role, k=5):
    # Підграф містить суми й контрагентів, тому публічна роль його не отримує.
    if role == "public":
        return ask(searcher, question, template, role=role, k=k)
    _, graph_text, graph_ids = graph.linearize(question)
    return ask(searcher, question, template, role=role, k=k, graph_text=graph_text, graph_ids=graph_ids)
