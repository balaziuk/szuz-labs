import io
from contextlib import redirect_stdout
from pathlib import Path

from neo4j.exceptions import ConstraintError

from run_cypher import ROOT, driver, run_file

COUNTS = """
CALL () { MATCH (n) RETURN count(n) AS nodes }
CALL () { MATCH ()-[r]->() RETURN count(r) AS rels }
RETURN nodes, rels
"""


def counts(s):
    rec = s.run(COUNTS).single()
    return rec["nodes"], rec["rels"]


def table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(r[h]) for h in header) + " |" for r in rows]
    return "\n".join(out)


def main():
    md = ["# Р2. Імпорт, обмеження та індекси\n"]
    with driver() as d, d.session() as s:
        n1, r1 = counts(s)
        md.append(f"## Кількість після першого імпорту\n\nВузлів: **{n1}**, зв'язків: **{r1}**.\n")

        labels = s.run("MATCH (n) UNWIND labels(n) AS label "
                       "RETURN label, count(*) AS count ORDER BY count DESC").data()
        md.append("### Вузли за мітками\n\n" + table(labels, ["label", "count"]) + "\n")
        types = s.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
                      "ORDER BY count DESC").data()
        md.append("### Зв'язки за типами\n\n" + table(types, ["type", "count"]) + "\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            run_file(s, ROOT / "import" / "01_constraints.cypher")
            run_file(s, ROOT / "import" / "02_import.cypher")
        created = sum(int(x) for x in __import__("re").findall(r"\+nodes (\d+)", buf.getvalue()))
        created_r = sum(int(x) for x in __import__("re").findall(r"\+rels (\d+)", buf.getvalue()))
        n2, r2 = counts(s)
        md.append("## Ідемпотентність (повторний запуск обох скриптів)\n\n"
                  f"| Стан | Вузлів | Зв'язків |\n|---|---|---|\n"
                  f"| Після 1-го імпорту | {n1} | {r1} |\n| Після 2-го імпорту | {n2} | {r2} |\n\n"
                  f"Під час повторного запуску створено вузлів: {created}, зв'язків: {created_r} "
                  f"→ {'ідемпотентність підтверджено' if (n1, r1) == (n2, r2) else 'Є ДУБЛІКАТИ'}.\n")

        cons = s.run("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
                     "RETURN name, type, labelsOrTypes, properties ORDER BY name").data()
        md.append("## SHOW CONSTRAINTS\n\n" + table(cons, ["name", "type", "labelsOrTypes", "properties"]) + "\n")
        idx = s.run("SHOW INDEXES YIELD name, type, labelsOrTypes, properties, owningConstraint "
                    "WHERE type <> 'LOOKUP' "
                    "RETURN name, type, labelsOrTypes, properties, owningConstraint ORDER BY name").data()
        md.append("## SHOW INDEXES\n\n" + table(idx, ["name", "type", "labelsOrTypes", "properties",
                                                       "owningConstraint"]) + "\n")

        md.append("## Приклад порушення обмеження\n")
        for title, q in [
            ("Дублікат id операції", "CREATE (:Operation {id: 'Op_00124', amount: 1.0})"),
            ("Дублікат номера рахунку",
             "CREATE (:Account {id: 'Acc_Fake', accountNumber: 'UA123456789'})"),
        ]:
            try:
                s.run(q).consume()
                md.append(f"**{title}:** `{q}` — несподівано виконано!\n")
            except ConstraintError as e:
                md.append(f"**{title}:**\n\n```cypher\n{q}\n```\n\nNeo4j відхилив запис:\n\n"
                          f"```\n{e.code}\n{e.message}\n```\n")
        n3, r3 = counts(s)
        md.append(f"Після спроб кількість не змінилася: {n3} вузлів, {r3} зв'язків.\n")

    (ROOT / "docs" / "import_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
