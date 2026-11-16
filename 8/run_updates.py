from pathlib import Path
from rdflib import Graph, Namespace

FIN = Namespace("http://example.org/financial-operations#")

PREFIXES = """
PREFIX fin:     <http://example.org/financial-operations#>
PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
"""

CHECK = PREFIXES + """
SELECT ?op ?opId ?amount ?account ?balance WHERE {
  fin:Acc_UA123456789 fin:balance ?balance .
  OPTIONAL {
    fin:Op_00134 fin:operationId ?opId ;
                 fin:amount ?amount ;
                 fin:belongsToAccount ?account .
    BIND(fin:Op_00134 AS ?op)
  }
}
"""


def short(t):
    if t is None:
        return "NULL"
    s = str(t)
    if s.startswith(str(FIN)):
        return "fin:" + s[len(str(FIN)):]
    return s


def snapshot(g, title):
    rows = list(g.query(CHECK))
    lines = [f"### {title}\n\n"]
    lines.append("| op | opId | amount | account | balance |\n| --- | --- | --- | --- | --- |\n")
    for row in rows:
        lines.append(
            f"| {short(row.op)} | {short(row.opId)} | {short(row.amount)} | "
            f"{short(row.account)} | {short(row.balance)} |\n"
        )
        print(
            title,
            f"op={short(row.op)} amount={short(row.amount)} balance={short(row.balance)}",
        )
    return "".join(lines)


def parse_updates(path="updates.rq"):
    text = Path(path).read_text(encoding="utf-8")
    updates = []
    for i in (1, 2):
        block = text.split(f"# BEGIN U{i}")[1].split(f"# END U{i}")[0].strip()
        updates.append(PREFIXES + "\n" + block)
    return updates


def main():
    g = Graph()
    g.parse("vocabulary.ttl", format="turtle")
    g.parse("data.ttl", format="turtle")

    md = ["# SPARQL UPDATE: стан до і після\n\n"]
    md.append(
        "Перевірочний SELECT: наявність `fin:Op_00134` та `fin:balance` "
        "рахунку `fin:Acc_UA123456789`.\n\n"
    )
    md.append("```sparql\n" + CHECK.strip() + "\n```\n\n")

    md.append(snapshot(g, "До оновлень"))
    md.append("\n")

    u1, u2 = parse_updates()
    g.update(u1)
    md.append("Виконано **U1** (INSERT DATA нової операції `fin:Op_00134`).\n\n")
    md.append(snapshot(g, "Після U1 (INSERT)"))
    md.append("\n")

    g.update(u2)
    md.append(
        "Виконано **U2** (DELETE/INSERT: залишок `9000.0` → `8250.0`).\n\n"
    )
    md.append(snapshot(g, "Після U2 (DELETE/INSERT балансу)"))
    md.append("\n")

    md.append("## Висновок\n\n")
    md.append(
        "До оновлень операції `Op_00134` не було, залишок рахунку — `9000.0`. "
        "Після U1 з’явилась витрата `750.0`^^xsd:decimal. "
        "Після U2 залишок став `8250.0`^^xsd:decimal "
        "(літерали з `.0`, щоб відповідати SHACL `sh:datatype xsd:decimal`).\n"
    )

    Path("before_after.md").write_text("".join(md), encoding="utf-8")
    print("Збережено before_after.md")


if __name__ == "__main__":
    main()
