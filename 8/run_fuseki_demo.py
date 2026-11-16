from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:3030/fin"
ROOT = Path(__file__).resolve().parent

PREFIXES = """
PREFIX fin:     <http://example.org/financial-operations#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def put_turtle(path: Path):
    body = path.read_bytes()
    url = f"{BASE}/data?default"
    return http(
        "PUT",
        url,
        data=body,
        headers={"Content-Type": "text/turtle; charset=utf-8"},
    )


def post_turtle(path: Path):
    body = path.read_bytes()
    return http(
        "POST",
        f"{BASE}/data?default",
        data=body,
        headers={"Content-Type": "text/turtle; charset=utf-8"},
    )


def sparql(query: str, accept="text/csv") -> str:
    qs = urllib.parse.urlencode({"query": query})
    return http(
        "GET",
        f"{BASE}/sparql?{qs}",
        headers={"Accept": accept},
    )


def update(update_text: str) -> str:
    return http(
        "POST",
        f"{BASE}/update",
        data=update_text.encode("utf-8"),
        headers={"Content-Type": "application/sparql-update; charset=utf-8"},
    )


def parse_queries():
    text = (ROOT / "queries.rq").read_text(encoding="utf-8")
    out = {}
    for i in range(1, 7):
        block = text.split(f"# BEGIN Q{i}")[1].split(f"# END Q{i}")[0].strip()
        out[f"Q{i}"] = PREFIXES + "\n" + block
    return out


def parse_updates():
    text = (ROOT / "updates.rq").read_text(encoding="utf-8")
    out = []
    for i in (1, 2):
        block = text.split(f"# BEGIN U{i}")[1].split(f"# END U{i}")[0].strip()
        out.append(PREFIXES + "\n" + block)
    return out


def main():
    lines = ["# Результати з Apache Jena Fuseki (`/fin`)\n\n"]
    lines.append("Сервер: `http://localhost:3030/fin` (конфіг без RDFS).\n\n")

    print("PUT vocabulary.ttl ...")
    put_turtle(ROOT / "vocabulary.ttl")
    print("POST data.ttl ...")
    post_turtle(ROOT / "data.ttl")

    count = sparql("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }").strip()
    print("triples:", count)
    lines.append(f"**Триплетів у default graph після завантаження:**\n```\n{count}\n```\n\n")

    inf = PREFIXES + """
SELECT ?x WHERE { ?x a fin:FinancialOperation } ORDER BY ?x
"""
    inf_csv = sparql(inf).strip()
    print("inference (no RDFS):\n", inf_csv)
    lines.append("## Виведення: SELECT `?x a fin:FinancialOperation` (без RDFS)\n\n")
    lines.append(f"```\n{inf_csv}\n```\n\n")
    lines.append(
        "_Очікувано порожньо (лише заголовок `x`). Для «після» — перезапуск із "
        "`fuseki-config-fin-rdfs.ttl` або CONSTRUCT з `inference_construct.rq`._\n\n"
    )

    for name, q in parse_queries().items():
        print("=" * 40, name)
        if "ASK {" in q or "\nASK" in q:
            body = "\n".join(
                ln for ln in q.splitlines()
                if ln.strip() and not ln.strip().startswith("PREFIX") and not ln.strip().startswith("#")
            ).lstrip()
            kind = body.split(None, 1)[0].upper()
        else:
            kind = "SELECT"
            body = "\n".join(
                ln for ln in q.splitlines()
                if ln.strip() and not ln.strip().startswith("PREFIX") and not ln.strip().startswith("#")
            ).lstrip()
            kind = body.split(None, 1)[0].upper()

        if kind == "ASK":
            res = sparql(q, accept="application/sparql-results+json")
            print(res)
            lines.append(f"## {name} (ASK)\n\n```json\n{res.strip()}\n```\n\n")
        elif kind == "CONSTRUCT":
            res = sparql(q, accept="text/turtle")
            print(res[:800])
            lines.append(f"## {name} (CONSTRUCT)\n\n```turtle\n{res.strip()}\n```\n\n")
        else:
            res = sparql(q, accept="text/csv")
            print(res)
            lines.append(f"## {name}\n\n```csv\n{res.strip()}\n```\n\n")

    check = PREFIXES + """
SELECT ?op ?opId ?amount ?balance WHERE {
  fin:Acc_UA123456789 fin:balance ?balance .
  OPTIONAL {
    fin:Op_00134 fin:operationId ?opId ; fin:amount ?amount .
    BIND(fin:Op_00134 AS ?op)
  }
}
"""
    lines.append("## UPDATE до/після\n\n")
    before = sparql(check).strip()
    print("BEFORE:\n", before)
    lines.append("### До\n\n```csv\n" + before + "\n```\n\n")

    u1, u2 = parse_updates()
    update(u1)
    mid = sparql(check).strip()
    print("AFTER U1:\n", mid)
    lines.append("### Після U1\n\n```csv\n" + mid + "\n```\n\n")
    update(u2)
    after = sparql(check).strip()
    print("AFTER U2:\n", after)
    lines.append("### Після U2\n\n```csv\n" + after + "\n```\n\n")

    out = ROOT / "fuseki_results.md"
    out.write_text("".join(lines), encoding="utf-8")
    print("Saved", out)


if __name__ == "__main__":
    main()
