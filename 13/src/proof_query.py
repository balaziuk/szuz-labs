"""Запит-доказ до графа з походженням (data/graph_load.ttl) і приклади записів gold / pred.

python src/proof_query.py          — SPARQL: скільки згадок, сутностей і згадок із повним походженням
python src/proof_query.py records  — по одному запису відношення з gold.jsonl, pred_rules.jsonl, pred_llm.jsonl
"""

import json
import sys
from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[1]
PREFIX = """PREFIX fin: <http://example.org/financial-operations#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""
COUNT = """SELECT (COUNT(?m) AS ?mentions) (COUNT(DISTINCT ?e) AS ?entities)
WHERE {
  ?m a prov:Entity ; fin:refersTo ?e ; fin:offsetStart ?off ;
     fin:model ?model ; fin:confidence ?conf ; prov:wasDerivedFrom ?src .
}"""
ALL = "SELECT (COUNT(?m) AS ?all) WHERE { ?m a prov:Entity }"
SAMPLE = """SELECT ?surface ?e ?src ?off ?model ?conf
WHERE {
  ?m a prov:Entity ; fin:surface ?surface ; fin:refersTo ?e ; fin:offsetStart ?off ;
     fin:model ?model ; fin:confidence ?conf ; prov:wasDerivedFrom ?src .
  FILTER(?src = fin:doc_d22 || ?src = fin:doc_d13)
}
ORDER BY ?src ?off
LIMIT 6"""


def short(term):
    return str(term).rsplit("#", 1)[-1]


def proof():
    graph = Graph().parse(ROOT / "data" / "graph_load.ttl")
    print(f"graph_load.ttl: {len(graph)} трійок")
    print(COUNT)
    mentions, entities = next(iter(graph.query(PREFIX + COUNT)))
    (total,) = next(iter(graph.query(PREFIX + ALL)))
    print(f"-> mentions={mentions} entities={entities}; усіх prov:Entity={total}, з повним походженням={mentions}")
    print()
    print("Приклад: згадки з документів d13 і d22 з походженням")
    for surface, entity, src, off, model, conf in graph.query(PREFIX + SAMPLE):
        print(f"  {short(src):<8} @{int(off):<4} «{surface}» -> {short(entity):<22} model={model} conf={float(conf):.2f}")


def records():
    for name in ("gold.jsonl", "pred_rules.jsonl", "pred_llm.jsonl"):
        rows = [json.loads(x) for x in (ROOT / "data" / name).read_text(encoding="utf-8").splitlines() if x.strip()]
        row = next(r for r in rows if r["kind"] == "relation")
        print(f"data/{name}: {len(rows)} записів; перше відношення:")
        print("  " + json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    records() if sys.argv[1:] == ["records"] else proof()
