from pathlib import Path
from rdflib import Graph, Namespace

FIN = Namespace("http://example.org/financial-operations#")

PREFIXES = """
PREFIX fin:     <http://example.org/financial-operations#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
"""


def short(term):
    s = str(term)
    if s.startswith(str(FIN)):
        return "fin:" + s[len(str(FIN)):]
    return s


def load_store():
    g = Graph()
    g.parse("vocabulary.ttl", format="turtle")
    g.parse("data.ttl", format="turtle")
    return g


def parse_queries(path="queries.rq"):
    text = Path(path).read_text(encoding="utf-8")
    queries = {}
    for i in range(1, 7):
        start = f"# BEGIN Q{i}"
        end = f"# END Q{i}"
        block = text.split(start)[1].split(end)[0].strip()
        queries[f"Q{i}"] = PREFIXES + "\n" + block
    return queries


def query_kind(q: str) -> str:
    body = "\n".join(
        line for line in q.splitlines()
        if line.strip() and not line.strip().startswith("PREFIX")
        and not line.strip().startswith("#")
    ).lstrip()
    first = body.split(None, 1)[0].upper()
    return first


def main():
    g = load_store()
    print(f"Граф: {len(g)} триплетів (vocabulary + data)\n")
    queries = parse_queries()
    out = ["# Результати SPARQL-запитів (фактичний запуск rdflib)\n"]

    for name, q in queries.items():
        print("=" * 60)
        print(name, f"({query_kind(q)})")
        print("=" * 60)
        out.append(f"## {name}\n\n")
        out.append("```sparql\n" + q.strip() + "\n```\n\n")
        kind = query_kind(q)

        if kind == "ASK":
            ans = bool(g.query(q))
            print(f"ASK → {ans}")
            out.append(f"**Результат ASK:** `{ans}`\n\n")
            continue

        if kind == "CONSTRUCT":
            cg = g.query(q)
            constructed = Graph()
            for t in cg:
                constructed.add(t)
            print(f"CONSTRUCT → {len(constructed)} триплетів")
            sample = []
            for i, (s, p, o) in enumerate(sorted(constructed, key=lambda t: str(t[2]))):
                if i >= 8:
                    break
                line = f"{short(s)} {short(p)} {short(o)} ."
                print(" ", line)
                sample.append(line)
            out.append(f"**Результат CONSTRUCT:** {len(constructed)} триплетів (перші 8):\n\n")
            out.append("```\n" + "\n".join(sample) + "\n```\n\n")
            continue

        res = g.query(q)
        vars_ = list(res.vars)
        rows = list(res)
        print(f"Рядків: {len(rows)}")
        out.append(f"**Рядків:** {len(rows)}\n\n")
        if rows:
            out.append("| " + " | ".join(str(v) for v in vars_) + " |\n")
            out.append("| " + " | ".join(["---"] * len(vars_)) + " |\n")
            for row in rows:
                cells = []
                for v in vars_:
                    val = row[v]
                    cells.append("NULL" if val is None else short(val))
                print(" | ".join(f"{v}={c}" for v, c in zip(vars_, cells)))
                out.append("| " + " | ".join(cells) + " |\n")
        out.append("\n")

    Path("query_results.md").write_text("".join(out), encoding="utf-8")
    print("\nЗбережено query_results.md")


if __name__ == "__main__":
    main()
