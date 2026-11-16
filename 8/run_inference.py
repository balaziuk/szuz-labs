from pathlib import Path
from rdflib import Graph, Namespace, RDF
from owlrl import RDFS_Semantics, DeductiveClosure

FIN = Namespace("http://example.org/financial-operations#")

SELECT_FO = """
PREFIX fin: <http://example.org/financial-operations#>
SELECT ?x WHERE {
  ?x a fin:FinancialOperation .
}
ORDER BY ?x
"""

CONSTRUCT_MATERIALIZE = """
PREFIX fin:  <http://example.org/financial-operations#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
CONSTRUCT {
  ?x rdf:type fin:FinancialOperation .
}
WHERE {
  ?x rdf:type ?c .
  ?c rdfs:subClassOf* fin:FinancialOperation .
  FILTER (?c != fin:FinancialOperation)
}
"""


def short(t):
    s = str(t)
    if s.startswith(str(FIN)):
        return "fin:" + s[len(str(FIN)):]
    return s


def select_rows(g):
    return [short(row.x) for row in g.query(SELECT_FO)]


def table(rows):
    if not rows:
        return "_Порожній результат._\n"
    lines = ["| x |\n| --- |\n"]
    for x in rows:
        lines.append(f"| {x} |\n")
    return "".join(lines)


def main():
    base = Graph()
    base.parse("vocabulary.ttl", format="turtle")
    base.parse("data.ttl", format="turtle")

    md = []
    md.append("# Демонстрація виведення (RDFS / CONSTRUCT-матеріалізація)\n\n")
    md.append(
        "Запит шукає ресурси з типом `fin:FinancialOperation`. "
        "У `data.ttl` операції мають лише типи `fin:Income` / `fin:Expense` "
        f"(усього **{len([1 for s,p,o in base if p==RDF.type and o in (FIN.Income, FIN.Expense)])}** операцій); "
        "у `vocabulary.ttl` задано `rdfs:subClassOf fin:FinancialOperation`.\n\n"
    )
    md.append("```sparql\n" + SELECT_FO.strip() + "\n```\n\n")

    rows0 = select_rows(base)
    print("Без виведення →", len(rows0))
    md.append("## 1. Без виведення (лише явно задані триплети)\n\n")
    md.append(f"Кількість рядків: **{len(rows0)}**\n\n")
    md.append(table(rows0))
    md.append("\n")

    md.append("## 2. Еквівалентна CONSTRUCT-матеріалізація\n\n")
    md.append(
        "Завдання дозволяє замість увімкнення Reasoner виконати CONSTRUCT, "
        "що додає виведені `rdf:type fin:FinancialOperation`. "
        "Нижче — саме цей підхід (підходить і для Fuseki без RDFS-резонеру).\n\n"
    )
    md.append("```sparql\n" + CONSTRUCT_MATERIALIZE.strip() + "\n```\n\n")

    constructed = Graph()
    for t in base.query(CONSTRUCT_MATERIALIZE):
        constructed.add(t)
    g_mat = Graph()
    for t in base:
        g_mat.add(t)
    for t in constructed:
        g_mat.add(t)

    rows_mat = select_rows(g_mat)
    print("Після CONSTRUCT-матеріалізації →", len(rows_mat), rows_mat)
    md.append(f"Додано триплетів CONSTRUCT: **{len(constructed)}**.\n\n")
    md.append(f"Той самий SELECT після злиття: **{len(rows_mat)}** рядків.\n\n")
    md.append(table(rows_mat))
    md.append("\n")

    g_rdfs = Graph()
    for t in base:
        g_rdfs.add(t)
    DeductiveClosure(RDFS_Semantics).expand(g_rdfs)
    rows_rdfs = select_rows(g_rdfs)
    print("З owlrl RDFS →", len(rows_rdfs))
    md.append("## 3. RDFS-виведення (owlrl — локальний аналог Reasoner)\n\n")
    md.append(
        "Для перевірки без GUI використано `owlrl.RDFS_Semantics`. "
        "У Fuseki варто повторити той самий SELECT на dataset `fin` "
        "**до** і **після** увімкнення RDFS / OWL-Horst і зробити скріншоти.\n\n"
    )
    md.append(f"Кількість рядків: **{len(rows_rdfs)}**\n\n")
    md.append(table(rows_rdfs))
    md.append("\n")

    md.append("## Висновок\n\n")
    md.append(
        f"Без виведення: **{len(rows0)}** результатів. "
        f"Після CONSTRUCT-матеріалізації: **{len(rows_mat)}**. "
        f"Після RDFS (owlrl): **{len(rows_rdfs)}**. "
        "Обидва підходи дають той самий ефект для цього запиту: підкласи "
        "`Income`/`Expense` стають видимими як `FinancialOperation`.\n\n"
    )
    md.append(
        "**Для звіту / скріншотів:** увімкнути RDFS у Fuseki на `fin` і "
        "зберегти результат SELECT до/після **або** виконати CONSTRUCT вище "
        "через `/fin/sparql` і показати SELECT після INSERT результатів CONSTRUCT.\n"
    )

    Path("inference_construct.rq").write_text(
        "# Матеріалізація rdf:type fin:FinancialOperation через rdfs:subClassOf*\n"
        + CONSTRUCT_MATERIALIZE.strip()
        + "\n",
        encoding="utf-8",
    )

    Path("inference_demo.md").write_text("".join(md), encoding="utf-8")
    print("Збережено inference_demo.md, inference_construct.rq")


if __name__ == "__main__":
    main()
