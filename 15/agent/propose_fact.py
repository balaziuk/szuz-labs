"""propose_fact: пропозиція нового знання → валідація (SHACL + джерело) → ризик → рішення.

Низький ризик приймається автоматично, середній чекає людину, високий відхиляється.
У сховище (data/kb_accepted.ttl) потрапляє лише прийняте й лише з provenance.
Кожна подія пишеться в data/audit.jsonl.

CLI:
  python agent/propose_fact.py propose '<json факту>'
  python agent/propose_fact.py review <fact_id> approve|reject "<хто>"
  python agent/propose_fact.py metrics
"""

import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

ROOT = Path(__file__).resolve().parents[1]
LABS = ROOT.parent
AUDIT = ROOT / "data" / "audit.jsonl"
PENDING = ROOT / "data" / "pending.json"
ACCEPTED = ROOT / "data" / "kb_accepted.ttl"
SHAPES = ROOT / "agent" / "fact_shapes.ttl"

HUB = Namespace("http://example.org/hub#")
PROV = Namespace("http://www.w3.org/ns/prov#")
SRC = Namespace("http://example.org/hub/source/")


def _now():
    return datetime.now(timezone.utc)


def _rows(name):
    with (LABS / "9" / "data" / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _known_sources():
    docs = {path.stem for path in (LABS / "13" / "data" / "docs").glob("d*.txt")}
    return docs | {row["id"] for row in _rows("operations.csv")}


def _audit(event, record, actor):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": _now().isoformat(), "event": event, "actor": actor, **record}
    with AUDIT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def to_graph(fact):
    graph = Graph()
    graph.bind("hub", HUB)
    graph.bind("prov", PROV)
    for row in _rows("counterparties.csv"):
        graph.add((HUB[row["id"]], RDF.type, HUB.Counterparty))
    node = HUB[f"fact_{fact['id']}"]
    graph.add((node, RDF.type, HUB.ProposedFact))
    if fact.get("kind"):
        graph.add((node, HUB.kind, Literal(fact["kind"])))
    if fact.get("source"):
        graph.add((node, PROV.wasDerivedFrom, SRC[fact["source"]]))
    if fact.get("proposed_by"):
        graph.add((node, PROV.wasAttributedTo, Literal(fact["proposed_by"])))
    payload = fact.get("payload") or {}
    if "surface" in payload:
        graph.add((node, HUB.surface, Literal(str(payload["surface"]), datatype=XSD.string)))
    if "target" in payload:
        graph.add((node, HUB.target, HUB[str(payload["target"])]))
    if "amount" in payload:
        graph.add((node, HUB.amount, Literal(str(payload["amount"]), datatype=XSD.decimal)))
    if "edrpou" in payload:
        graph.add((node, HUB.edrpou, Literal(str(payload["edrpou"]))))
    return graph, node


def validate(fact):
    """SHACL + перевірка, що джерело справді є в хабі."""
    graph, _node = to_graph(fact)
    conforms, report_graph, _text = shacl_validate(graph, shacl_graph=str(SHAPES), inference="none")
    errors = []
    if not conforms:
        for message in report_graph.objects(None, URIRef("http://www.w3.org/ns/shacl#resultMessage")):
            errors.append(f"SHACL: {message}")
    if fact.get("source") and fact["source"] not in _known_sources():
        errors.append(f"джерела {fact['source']} немає серед документів і операцій хаба")
    return sorted(set(errors))


def classify_risk(fact):
    """Ризик рахує код, а не той, хто пропонує."""
    kind = fact.get("kind")
    payload = fact.get("payload") or {}
    if kind == "identifier_change":
        return "high", "зміна ідентифікатора контрагента"
    if kind == "amount_note":
        opposes = payload.get("opposes")
        if opposes:
            amounts = {row["id"]: float(row["amount"]) for row in _rows("operations.csv")}
            if opposes in amounts and abs(amounts[opposes] - float(payload.get("amount") or 0)) > 0.005:
                return "medium", f"сума суперечить операції {opposes} ({amounts[opposes]:.2f})"
        return "medium", "нова сума впливає на звіти"
    if kind == "alias":
        return "low", "аліас до наявного контрагента"
    return "high", "невідомий вид факту"


def _load_pending():
    return json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else {}


def _save_pending(pending):
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_accepted(fact, approved_by, decided_at):
    graph = Graph()
    if ACCEPTED.exists():
        graph.parse(ACCEPTED, format="turtle")
    graph.bind("hub", HUB)
    graph.bind("prov", PROV)
    fact_graph, node = to_graph(fact)
    for triple in fact_graph.triples((node, None, None)):
        graph.add(triple)
    graph.set((node, RDF.type, HUB.AcceptedFact))
    graph.add((node, PROV.generatedAtTime, Literal(decided_at, datatype=XSD.dateTime)))
    graph.add((node, HUB.approvedBy, Literal(approved_by)))
    for alternative in fact.get("alternatives") or []:
        graph.add((node, HUB.alternative, Literal(alternative)))
    graph.serialize(ACCEPTED, format="turtle")


def propose(fact):
    proposed_at = _now().isoformat()
    errors = validate(fact)
    risk, reason = classify_risk(fact)
    record = {"fact_id": fact["id"], "kind": fact.get("kind"), "risk": risk, "risk_reason": reason, "errors": errors, "source": fact.get("source"), "proposed_at": proposed_at}
    if errors:
        status = "rejected_invalid"
    elif risk == "low":
        status = "auto_accepted"
        _write_accepted(fact, "auto (низький ризик)", proposed_at)
    elif risk == "medium":
        status = "pending"
        pending = _load_pending()
        pending[fact["id"]] = {"fact": fact, "record": record}
        _save_pending(pending)
    else:
        status = "rejected_high_risk"
    record["status"] = status
    _audit("propose", record, fact.get("proposed_by", "agent"))
    return record


def review(fact_id, decision, reviewer):
    pending = _load_pending()
    if fact_id not in pending:
        raise KeyError(f"{fact_id} немає в черзі")
    item = pending.pop(fact_id)
    _save_pending(pending)
    decided_at = _now().isoformat()
    record = dict(item["record"])
    record["decided_at"] = decided_at
    record["wait_s"] = round((datetime.fromisoformat(decided_at) - datetime.fromisoformat(record["proposed_at"])).total_seconds(), 2)
    if decision == "approve":
        record["status"] = "approved_by_human"
        _write_accepted(item["fact"], reviewer, decided_at)
    else:
        record["status"] = "rejected_by_human"
    _audit("review", record, reviewer)
    return record


def metrics():
    rows = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines() if line.strip()] if AUDIT.exists() else []
    proposals = [row for row in rows if row["event"] == "propose"]
    reviews = [row for row in rows if row["event"] == "review"]
    final = {row["fact_id"]: row["status"] for row in proposals}
    final.update({row["fact_id"]: row["status"] for row in reviews})
    total = len(final) or 1
    accepted = sum(1 for status in final.values() if status in {"auto_accepted", "approved_by_human"})
    waits = [row["wait_s"] for row in reviews]
    return {
        "proposals": len(final),
        "accepted_share": round(accepted / total, 3),
        "auto_share": round(sum(1 for s in final.values() if s == "auto_accepted") / total, 3),
        "human_reviewed": len(reviews),
        "human_approved_share": round(sum(1 for r in reviews if r["status"] == "approved_by_human") / (len(reviews) or 1), 3),
        "rejected": sum(1 for s in final.values() if s.startswith("rejected")),
        "pending": len(_load_pending()),
        "median_wait_s": statistics.median(waits) if waits else None,
    }


def reset():
    for path in (AUDIT, PENDING, ACCEPTED):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "metrics"
    if command == "propose":
        print(json.dumps(propose(json.loads(sys.argv[2])), ensure_ascii=False, indent=2))
    elif command == "review":
        print(json.dumps(review(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "owner"), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(metrics(), ensure_ascii=False, indent=2))
