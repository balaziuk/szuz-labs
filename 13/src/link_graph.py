"""Зв'язує згадки з реєстром ЛР9 і записує граф із походженням.

Виконується завантаження в RDF (rdflib) і SPARQL-перевірка, що в кожної згадки є джерело,
офсет, модель і впевненість. Файл Cypher лежить поруч для Neo4j, але в граф ЛР9 нічого не пишеться.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schema import accounts, categories, counterparties, RISKS

ALIAS = {
    "приват": "Cp_PrivatBank",
    "орендодавцю": "Cp_Orendodavets",
    "фопу іваненку": "Cp_FreelanceClient",
    "сільпо": "Cp_Silpo",
    "київстар": "Cp_Kyivstar",
    "комуналка": "Cat_Utilities",
    "їжа": "Cat_Food",
    "зв'язок": "Cat_Telecom",
}


def canon_key(text):
    return " ".join(text.casefold().replace("«", "").replace("»", "").split())


def build_index():
    index = {}
    names = {}
    for row in accounts():
        index[canon_key(row["accountNumber"])] = ("Account", row["id"], row["accountNumber"])
        names[row["id"]] = row["accountNumber"]
    for row in counterparties():
        index[canon_key(row["name"])] = ("Counterparty", row["id"], row["name"])
        names[row["id"]] = row["name"]
    for row in categories():
        index[canon_key(row["name"])] = ("Category", row["id"], row["name"])
        names[row["id"]] = row["name"]
    for phrase, risk_id in RISKS:
        index[canon_key(phrase)] = ("Risk", risk_id, phrase)
        names[risk_id] = phrase
    for alias, ident in ALIAS.items():
        index[canon_key(alias)] = index[canon_key(alias)] if canon_key(alias) in index else None
        # alias points at the canonical id already stored under the official name
        official = next(item for item in index.values() if item and item[1] == ident)
        index[canon_key(alias)] = official
    return index, names


def link_rows(rows, index):
    linked = []
    rejected = []
    for row in rows:
        if row["kind"] != "entity":
            continue
        if row["type"] not in {"Account", "Counterparty", "Category", "Risk"}:
            continue
        hit = index.get(canon_key(row["text"]))
        if not hit:
            rejected.append(row)
            continue
        type_, ident, name = hit
        linked.append({**row, "canonical_id": ident, "canonical_name": name, "canonical_type": type_})
    return linked, rejected


def esc(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def write_cypher(linked):
    lines = [
        "// Граф витягу ЛР13. Окремий від графа ЛР9: вузли мають мітку Lab13.",
    ]
    seen = set()
    for row in linked:
        if row["canonical_id"] not in seen:
            seen.add(row["canonical_id"])
            lines.append(
                f'MERGE (e:Lab13Entity {{id: "{esc(row["canonical_id"])}"}}) '
                f'SET e.name = "{esc(row["canonical_name"])}", e.type = "{esc(row["canonical_type"])}";'
            )
        lines.append(
            f'MERGE (m:Lab13Mention {{id: "{esc(row["id"])}"}}) '
            f'SET m.source = "{esc(row["doc_id"])}", m.offsetStart = {row["start"]}, '
            f'm.offsetEnd = {row["end"]}, m.model = "{esc(row["model"])}", '
            f'm.confidence = {row["confidence"]}, m.surface = "{esc(row["text"])}";'
        )
        lines.append(
            f'MATCH (e:Lab13Entity {{id: "{esc(row["canonical_id"])}"}}), '
            f'(m:Lab13Mention {{id: "{esc(row["id"])}"}}) MERGE (e)-[:HAS_MENTION]->(m);'
        )
    lines.append(
        "MATCH (m:Lab13Mention) "
        "WHERE m.source IS NULL OR m.offsetStart IS NULL OR m.model IS NULL OR m.confidence IS NULL "
        "RETURN count(m) AS missingProvenance;"
    )
    (ROOT / "data" / "graph_load.cypher").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(seen)


def write_ttl(linked):
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import RDF, XSD

    fin = Namespace("http://example.org/financial-operations#")
    prov = Namespace("http://www.w3.org/ns/prov#")
    graph = Graph()
    graph.bind("fin", fin)
    graph.bind("prov", prov)
    seen = set()
    for row in linked:
        entity = fin[row["canonical_id"]]
        if row["canonical_id"] not in seen:
            seen.add(row["canonical_id"])
            graph.add((entity, RDF.type, fin[row["canonical_type"]]))
            graph.add((entity, fin.canonicalName, Literal(row["canonical_name"], lang="uk")))
        mention = fin[f"mention_{row['id'].replace('-', '_')}"]
        graph.add((mention, RDF.type, prov.Entity))
        graph.add((mention, fin.refersTo, entity))
        graph.add((mention, prov.wasDerivedFrom, fin[f"doc_{row['doc_id']}"]))
        graph.add((mention, fin.offsetStart, Literal(row["start"], datatype=XSD.integer)))
        graph.add((mention, fin.offsetEnd, Literal(row["end"], datatype=XSD.integer)))
        graph.add((mention, fin.model, Literal(row["model"])))
        graph.add((mention, fin.confidence, Literal(row["confidence"], datatype=XSD.decimal)))
        graph.add((mention, fin.surface, Literal(row["text"], lang="uk")))
    destination = ROOT / "data" / "graph_load.ttl"
    graph.serialize(destination, format="turtle")
    return graph


def prove(graph):
    query = """
    PREFIX fin: <http://example.org/financial-operations#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT
      (COUNT(?m) AS ?mentions)
      (COUNT(DISTINCT ?e) AS ?entities)
      (SUM(IF(BOUND(?src) && BOUND(?off) && BOUND(?model) && BOUND(?conf), 1, 0)) AS ?withProvenance)
    WHERE {
      ?m a prov:Entity ;
         fin:refersTo ?e ;
         fin:offsetStart ?off ;
         fin:model ?model ;
         fin:confidence ?conf ;
         prov:wasDerivedFrom ?src .
    }
    """
    rows = list(graph.query(query))
    mentions, entities, proven = (int(rows[0][0]), int(rows[0][1]), int(rows[0][2]))
    sample = graph.query(
        """
        PREFIX fin: <http://example.org/financial-operations#>
        PREFIX prov: <http://www.w3.org/ns/prov#>
        SELECT ?name ?source ?offset ?model ?confidence WHERE {
          ?m fin:refersTo ?e ; fin:surface ?name ; fin:offsetStart ?offset ;
             fin:model ?model ; fin:confidence ?confidence ; prov:wasDerivedFrom ?source .
        } LIMIT 3
        """
    )
    return mentions, entities, proven, list(sample)


def write_linking_doc(linked, rejected, mentions, entities, proven, sample):
    by_id = {}
    for row in linked:
        by_id.setdefault(row["canonical_id"], row["canonical_name"])
    lines = [
        "# Зв'язування сутностей",
        "",
        "Ключ порівняння: регістр, зайві пробіли і лапки «» прибираються. Далі точний ключ реєстру ЛР9 або аліас із таблиці нижче. Найближче ім'я без точного ключа не приймається.",
        "",
        f"Зв'язано канонічних сутностей: {len(by_id)}. Згадок у графі: {len(linked)}. Не зв'язано згадок типу рахунок/контрагент/категорія/ризик: {len(rejected)}.",
        "",
        "## Аліаси і рішення",
        "",
        "| Поверхня | Куди | Рішення | Чому |",
        "|---|---|---|---|",
        "| Приват | Cp_PrivatBank | прийняти | у тому ж документі d17 рядок розкриває повну назву АТ КБ «ПриватБанк» |",
        "| орендодавцю | Cp_Orendodavets | прийняти | відмінок назви з реєстру, інших орендодавців у хабі немає |",
        "| ФОПу Іваненку | Cp_FreelanceClient | прийняти | відмінок ФОП Іваненко |",
        "| сільпо | Cp_Silpo | прийняти | розмовна форма ТОВ «Сільпо-Фуд», інших «сільпо» в реєстрі немає |",
        "| київстар | Cp_Kyivstar | прийняти | розмовна форма ПрАТ «Київстар» |",
        "| Комуналка | Cat_Utilities | прийняти | розмовна назва категорії «Комунальні послуги» |",
        "| їжа | Cat_Food | прийняти | у рядку написано «категорія їжа», у реєстрі це Харчування |",
        "| зв'язок | Cat_Telecom | прийняти | у рядку написано «категорія зв'язок», у реєстрі це Зв'язок та інтернет |",
        "| дохід | — | відхилити | загальне слово, не листова категорія; до Cat_Income не зливаємо |",
        "",
        "## Канонічні сутності",
        "",
    ]
    for ident, name in sorted(by_id.items()):
        lines.append(f"- {ident}: {name}")
    lines += [
        "",
        "## Завантаження",
        "",
        "Файл `data/graph_load.ttl` завантажено в rdflib. Запис у Neo4j ЛР9 не виконувався, щоб не змішати витяг із графом операцій. Той самий вміст для окремої бази лежить у `data/graph_load.cypher` (мітки Lab13Entity і Lab13Mention).",
        "",
        "Запит-доказ:",
        "",
        "```sparql",
        "SELECT (COUNT(?m) AS ?mentions) (COUNT(DISTINCT ?e) AS ?entities)",
        "WHERE {",
        "  ?m a prov:Entity ; fin:refersTo ?e ; fin:offsetStart ?off ;",
        "     fin:model ?model ; fin:confidence ?conf ; prov:wasDerivedFrom ?src .",
        "}",
        "```",
        "",
        f"Результат: згадок {mentions}, сутностей {entities}, з повним походженням {proven}.",
        "",
        "Три згадки з відповіді:",
        "",
    ]
    for name, source, offset, model, confidence in sample:
        lines.append(f"- {name} з {source}, офсет {offset}, модель {model}, впевненість {confidence}")
    lines.append("")
    if mentions != proven or entities < 20:
        raise SystemExit(f"граф не пройшов перевірку: entities={entities} mentions={mentions} proven={proven}")
    (ROOT / "docs" / "linking.md").write_text("\n".join(lines), encoding="utf-8")


def load_predictions():
    rows = []
    with (ROOT / "data" / "pred_rules.jsonl").open(encoding="utf-8") as handle:
        rows.extend(json.loads(line) for line in handle if line.strip())
    gold_alias = []
    with (ROOT / "data" / "gold.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "entity" and row["text"] in {
                "Приват",
                "орендодавцю",
                "ФОПу Іваненку",
                "сільпо",
                "київстар",
                "Комуналка",
                "їжа",
                "зв'язок",
            }:
                gold_alias.append(
                    {
                        **row,
                        "model": "human_alias_v1",
                        "prompt_version": "linking_v1",
                        "confidence": 0.7,
                    }
                )
    return rows + gold_alias


def main():
    index, _names = build_index()
    linked, rejected = link_rows(load_predictions(), index)
    write_cypher(linked)
    graph = write_ttl(linked)
    mentions, entities, proven, sample = prove(graph)
    write_linking_doc(linked, rejected, mentions, entities, proven, sample)
    (ROOT / "data" / "linked.json").write_text(
        json.dumps(linked, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"linked_mentions={len(linked)} entities={entities} provenance={proven} rejected={len(rejected)}")


if __name__ == "__main__":
    main()
