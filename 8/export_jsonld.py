import json
from pathlib import Path

from rdflib import XSD, Graph, Literal

BASE = Path(__file__).parent

CONTEXT = {
    "fin": "http://example.org/financial-operations#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
}


def main():
    g = Graph()
    g.parse(BASE / "data.ttl", format="turtle")

    (BASE / "context.jsonld").write_text(
        json.dumps({"@context": CONTEXT}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out = BASE / "data.jsonld"
    out.write_text(g.serialize(format="json-ld", context=CONTEXT, indent=2), encoding="utf-8")

    back = Graph()
    back.parse(out, format="json-ld")
    doc = json.loads(out.read_text(encoding="utf-8"))
    nodes = doc.get("@graph", [doc])
    print(f"data.jsonld: вузлів {len(nodes)}, триплетів {len(back)} (у data.ttl {len(g)})")
    def norm(graph):
        return {
            (s, p, Literal(str(o)) if isinstance(o, Literal) and o.datatype == XSD.string else o)
            for s, p, o in graph
        }

    print("Графи збігаються:", norm(g) == norm(back))


if __name__ == "__main__":
    main()
