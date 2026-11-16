"""Порівняння baseline і стану після покращень + вплив на RAG.

1. Метрики якості до/після: provenance у копії RDF, канонічні контрагенти, дедуплікація.
2. Офіційні метрики RAG ЛР11 (docs/rag_eval.md) — набір питань ЛР11 не зачіпає виправлені дефекти.
3. Цільовий прогін: графовий лінкер RAG ЛР11 (11/src/graph_context.py) на 10 питаннях з
   розмовними назвами контрагентів — до дедуплікації, з ручними синонімами ЛР11, з аліасами
   дедуплікації (поріг) і з аліасами після LLM-судді. Генерація LLM тут не потрібна:
   міряється контекст, який отримав би генератор (context recall / precision).
"""

import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rdflib import Literal, URIRef
from rdflib.namespace import RDF

from quality.common import LABS, edges_by_start, load_rdf, operations, read_csv
from quality.dedup import RECORDS, UnionFind, blocks, combined
from quality.gate import FIN

QUESTIONS = [
    ("q01", "Який ЄДРПОУ у Приват?", "Cp_PrivatBank"),
    ("q02", "Скільки сплачено орендодавцю у жовтні 2026?", "Cp_Orendodavets"),
    ("q03", "Що купували в сільпо у квітні?", "Cp_Silpo"),
    ("q04", "Скільки платили ФОПу Іваненку?", "Cp_FreelanceClient"),
    ("q05", "Скільки коштує київстар на місяць?", "Cp_Kyivstar"),
    ("q06", "Які поїздки були через уклон?", "Cp_Uklon"),
    ("q07", "Скільки виставили Київські комунальні за жовтень?", "Cp_Utility"),
    ("q08", "Що відомо про Діджитал Студіо?", "Cp_DigitalStudio"),
    ("q09", "Скільки витрачено в АТБ-Маркет?", "Cp_ATB"),
    ("q10", "Чи купували ліки в Аптека АНЦ?", "Cp_Apteka"),
]


def rag_numbers():
    """Метрики ЛР11 з 11/docs/rag_eval.md; знімок у quality/rag_lab11.json — для клону без 11/docs (не в git)."""
    source = LABS / "11" / "docs" / "rag_eval.md"
    snapshot = ROOT / "quality" / "rag_lab11.json"
    if not source.exists():
        return json.loads(snapshot.read_text(encoding="utf-8"))
    text = source.read_text(encoding="utf-8")
    patterns = {
        "faithfulness": r"faithfulness \(суддя[^|]*\| ([0-9.]+)",
        "context_recall": r"context recall \| ([0-9.]+)",
        "abstention": r"abstention rate[^|]*\| ([0-9.]+)",
    }
    numbers = {name: float(re.search(pattern, text).group(1)) for name, pattern in patterns.items()}
    snapshot.write_text(json.dumps(numbers, ensure_ascii=False, indent=2), encoding="utf-8")
    return numbers


def all_metrics_after():
    """Ті самі 10 метрик baseline, переміряні тими самими функціями profile.py; RDF-метрики — на store_after.ttl."""
    from rdflib import Graph

    from quality import profile

    edges = edges_by_start()
    graph = Graph().parse(ROOT / "quality" / "store_after.ttl", format="turtle")
    sample = list(read_csv_path(ROOT / "quality" / "accuracy_sample.csv"))
    reports, report_n = profile.report_consistency(graph)
    return {
        "частка безготівкових витрат із контрагентом": profile.counterparty_fill(edges)[0],
        "deviation = actual − planned": profile.budget_consistency()[0],
        "звіт дорівнює сумі своїх витрат": reports,
        "експертна вибірка 30 записів": sum(1 for row in sample if row["expert"] == "ok") / len(sample),
        "дата є і не пізніше 2026-11-03": profile.timeliness()[0],
        "унікальність точної назви контрагента": profile.uniqueness()[0],
        "DERIVED_FROM у CSV-графі": profile.provenance(edges)[0],
        "prov:wasDerivedFrom у RDF": profile.rdf_provenance(graph)[0],
        "рахунки, ЄДРПОУ, додатні суми": profile.validity()[0],
        "Turtle читається і SPARQL повертає звіти": 1.0 if report_n else 0.0,
    }


def read_csv_path(path):
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def provenance_after():
    graph = load_rdf()
    edges = edges_by_start()
    ops = {row["id"]: row for row in operations()}
    added = 0
    for kind in (FIN.Expense, FIN.Income):
        for node in graph.subjects(RDF.type, kind):
            op_id = str(node).rsplit("#", 1)[-1]
            source = next((edge["end"] for edge in edges.get(op_id, []) if edge["type"] == "DERIVED_FROM"), None)
            if source is None and op_id in ops:
                source = "Src_FromCsv"
            if source:
                graph.add((node, URIRef("http://www.w3.org/ns/prov#wasDerivedFrom"), Literal(source)))
                added += 1
    query = """
    PREFIX fin: <http://example.org/financial-operations#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    SELECT ?op ?src WHERE {
      VALUES ?kind { fin:Expense fin:Income }
      ?op a ?kind .
      OPTIONAL { ?op prov:wasDerivedFrom ?src }
    }
    """
    rows = list(graph.query(query))
    with_source = sum(1 for _op, src in rows if src is not None)
    graph.serialize(ROOT / "quality" / "store_after.ttl", format="turtle")
    return with_source / len(rows) if rows else 0.0, added


# ---------- цільовий RAG ----------

def lab11_graph_module():
    path = LABS / "11" / "src" / "graph_context.py"
    spec = importlib.util.spec_from_file_location("lab11_graph_context", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def surface_key(name):
    key = name.casefold().replace("«", "").replace("»", "").strip()
    key = re.sub(r"^(тов|прат|ат кб|ат|фоп|го)\s+", "", key)
    return key


def clusters(judged):
    """Кластери записів RECORDS: за порогом або з рішенням судді на спірних парах."""
    report = json.loads((ROOT / "quality" / "dedup_report.json").read_text(encoding="utf-8"))
    merges = json.loads((ROOT / "quality" / "merges.json").read_text(encoding="utf-8"))
    verdicts = merges.get("judge", {}) if judged else {}
    records = {r[0]: {"id": r[0], "name": r[1], "edrpou": r[2]} for r in RECORDS}
    union = UnionFind(records)
    with (ROOT / "quality" / "pairs_gold.csv").open(encoding="utf-8", newline="") as handle:
        pairs = list(csv.DictReader(handle))
    for row in pairs:
        left, right = records[row["left_id"]], records[row["right_id"]]
        score = combined(left, right) if blocks(left, right) else 0.0
        if row["pair_id"] in verdicts:
            score = 1.0 if verdicts[row["pair_id"]]["duplicate"] else 0.0
        if score >= report["threshold"]:
            union.union(row["left_id"], row["right_id"])
    groups = {}
    for record_id in records:
        groups.setdefault(union.find(record_id), []).append(record_id)
    return list(groups.values())


def alias_table(groups):
    """Поверхня → множина id реєстру, на які вказує її кластер."""
    registry = {row["name"]: row["id"] for row in read_csv("counterparties.csv")}
    names = {r[0]: r[1] for r in RECORDS}
    table = {}
    for group in groups:
        ids = {registry[names[rid]] for rid in group if names[rid] in registry}
        for rid in group:
            key = surface_key(names[rid])
            if len(key) >= 4 and ids:
                table.setdefault(key, set()).update(ids)
    return table


def rag_probe():
    module = lab11_graph_module()
    graph = module.Graph(backend="csv")
    synonyms = list(module.SYNONYMS)
    tables = {"rule": alias_table(clusters(False)), "judge": alias_table(clusters(True))}
    configs = ["registry", "lab11_synonyms", "rule", "judge"]
    rows = []
    for qid, question, expected in QUESTIONS:
        seeds_by = {}
        module.SYNONYMS = []
        seeds_by["registry"] = graph.link(question)
        module.SYNONYMS = synonyms
        seeds_by["lab11_synonyms"] = graph.link(question)
        module.SYNONYMS = []
        base = graph.link(question)
        folded = question.casefold()
        for name in ("rule", "judge"):
            seeds = list(base)
            for key, ids in sorted(tables[name].items(), key=lambda item: -len(item[0])):
                if key in folded:
                    seeds.extend(sorted(i for i in ids if i not in seeds))
            seeds_by[name] = seeds
        module.SYNONYMS = synonyms
        row = {"id": qid, "question": question, "expected": expected}
        for name in configs:
            counterparties = [s for s in seeds_by[name] if s.startswith("Cp_")]
            row[name] = {
                "seeds": seeds_by[name],
                "recall": 1.0 if expected in seeds_by[name] else 0.0,
                "precision": counterparties.count(expected) / len(counterparties) if counterparties else None,
                "wrong": [s for s in counterparties if s != expected],
            }
        rows.append(row)
    summary = {}
    for name in configs:
        found = [r[name] for r in rows]
        with_cp = [f for f in found if any(s.startswith("Cp_") for s in f["seeds"])]
        summary[name] = {
            "context_recall": sum(f["recall"] for f in found) / len(found),
            "context_precision": sum(f["precision"] for f in with_cp) / len(with_cp) if with_cp else None,
            "wrong_seeds": sum(len(f["wrong"]) for f in found),
        }
    (ROOT / "quality" / "rag_probe.json").write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows, summary


def fmt(value):
    return "—" if value is None else f"{value:.2f}"


def main():
    baseline = json.loads((ROOT / "quality" / "metrics.json").read_text(encoding="utf-8"))
    dedup = json.loads((ROOT / "quality" / "dedup_report.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item["value"] for item in baseline["metrics"]}
    prov_after, added = provenance_after()
    before_entities = len(RECORDS)
    after_rule = len(clusters(False))
    after_judge = len(clusters(True))
    rag = rag_numbers()
    after_all = {name: round(value, 4) for name, value in all_metrics_after().items()}  # як у metrics.json
    baseline_metrics = json.loads((ROOT / "quality" / "metrics.json").read_text(encoding="utf-8"))["metrics"]
    rows, summary = rag_probe()
    s = summary
    lines = [
        "# Після покращення",
        "",
        "Baseline — `quality/metrics.json`, версія baseline-1 від 2026-11-03. Після — копія RDF з походженням (`quality/store_after.ttl`), злиття аліасів (`quality/merges.json`) і LLM-суддя на спірних парах. Файли ЛР8 і ЛР9 не змінювались.",
        "",
        "## Якість до і після",
        "",
        "| Метрика | До | Після (поріг) | Після (поріг + суддя) |",
        "|---|---:|---:|---:|",
        f"| частка RDF-операцій із prov:wasDerivedFrom | {by_name['prov:wasDerivedFrom у RDF']:.3f} | {prov_after:.3f} | {prov_after:.3f} |",
        f"| записів назв → канонічних контрагентів | {before_entities} → {before_entities} | {before_entities} → {after_rule} | {before_entities} → {after_judge} |",
        f"| precision дедуплікації на test | — | {dedup['test']['precision']:.3f} | {dedup['test_with_judge']['precision']:.3f} |",
        f"| recall дедуплікації на test | — | {dedup['test']['recall']:.3f} | {dedup['test_with_judge']['recall']:.3f} |",
        "",
        "",
        "Усі 10 метрик baseline переміряно тими самими функціями `profile.py`; метрики RDF — на копії `store_after.ttl`:",
        "",
        "| Метрика | Вимір | Поріг | До | Після | Зміна |",
        "|---|---|---:|---:|---:|---|",
        *[
            f"| {m['name']} | {m['dimension']} | {m['threshold']} | {m['value']:.3f} | {after_all[m['name']]:.3f} | "
            + ("покращено" if after_all[m['name']] > m['value'] + 1e-9 else "без змін" if abs(after_all[m['name']] - m['value']) < 1e-9 else "гірше")
            + " |"
            for m in baseline_metrics
        ],
        "",
        f"Справжніх канонічних контрагентів у брудному списку 12. Злиття за порогом дає {after_rule}, бо «Київстар» і «Київські комунальні» склеюються через спільне «київ». Суддя на спірних парах розводить їх ({after_judge}).",
        f"У копію RDF дописано {added} ребер походження з CSV (`DERIVED_FROM`).",
        "",
        "## RAG до і після",
        "",
        "### Офіційний набір ЛР11",
        "",
        "Числа взято з прогону ЛР11 (`11/docs/rag_eval.md`), роль аналітика, промпт rag_v1. Тридцять питань ЛР11 стосуються визначень і документів корпусу, а не аліасів контрагентів чи жовтневої комуналки, тому виправлення ЛР14 їх не зачіпають, і повторний прогін дав би ті самі відповіді з кешу.",
        "",
        "| Метрика RAG | До | Після |",
        "|---|---:|---:|",
        f"| faithfulness (суддя) | {rag['faithfulness']:.3f} | {rag['faithfulness']:.3f} |",
        f"| context recall | {rag['context_recall']:.3f} | {rag['context_recall']:.3f} |",
        f"| abstention | {rag['abstention']:.3f} | {rag['abstention']:.3f} |",
        "",
        "### Цільовий прогін графового контексту ЛР11",
        "",
        "Щоб побачити вплив саме виправлених дефектів, графовий лінкер RAG ЛР11 (`Graph.link`, бекенд CSV) прогнано на 10 питаннях із розмовними назвами контрагентів. Context recall — чи потрапив потрібний контрагент у насіння підграфа, яке отримує генератор; context precision — частка правильних серед знайдених контрагентів.",
        "",
        "| Конфігурація | context recall | context precision | хибних контрагентів |",
        "|---|---:|---:|---:|",
        f"| реєстр без аліасів (до) | {s['registry']['context_recall']:.2f} | {fmt(s['registry']['context_precision'])} | {s['registry']['wrong_seeds']} |",
        f"| ручні синоніми ЛР11 | {s['lab11_synonyms']['context_recall']:.2f} | {fmt(s['lab11_synonyms']['context_precision'])} | {s['lab11_synonyms']['wrong_seeds']} |",
        f"| аліаси дедуплікації, поріг | {s['rule']['context_recall']:.2f} | {fmt(s['rule']['context_precision'])} | {s['rule']['wrong_seeds']} |",
        f"| аліаси дедуплікації, поріг + суддя (після) | {s['judge']['context_recall']:.2f} | {fmt(s['judge']['context_precision'])} | {s['judge']['wrong_seeds']} |",
        "",
        "| id | питання | очікуваний | до | синоніми ЛР11 | поріг | поріг + суддя |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = [", ".join(s_ for s_ in row[name]["seeds"] if s_.startswith("Cp_")) or "—" for name in ("registry", "lab11_synonyms", "rule", "judge")]
        lines.append(f"| {row['id']} | {row['question']} | {row['expected']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Faithfulness і abstention на цьому прогоні не міряються: генерацію не запускали, бо виправлення змінюють саме контекст, який отримує генератор. Повний прогін із генерацією — `python 11/src/run_all.py` з цими питаннями (обмеження цього звіту).",
        "",
        "## Аналіз впливу",
        "",
        f"1. **Дедуплікація аліасів дала найбільший ефект для RAG.** Context recall цільових питань зріс з {s['registry']['context_recall']:.2f} (реєстр) до {s['judge']['context_recall']:.2f}. Ручний список синонімів ЛР11 закривав частину ({s['lab11_synonyms']['context_recall']:.2f}), але його треба було дописувати руками; аліаси з дедуплікації виводяться з даних.",
        f"2. **Хибне злиття шкодить точності контексту, суддя це виправляє.** За самим порогом «Київстар» тягне в контекст і «Київські комунальні» (precision {fmt(s['rule']['context_precision'])}, хибних {s['rule']['wrong_seeds']}). LLM-суддя розводить пару за різними ЄДРПОУ: precision {fmt(s['judge']['context_precision'])}. Ціна — один пропущений справжній дублікат на test (recall дедуплікації {dedup['test_with_judge']['recall']:.3f}).",
        f"3. **Provenance у RDF ({by_name['prov:wasDerivedFrom у RDF']:.3f} → {prov_after:.3f}) не змінив метрик ЛР11**, бо той набір не цитує Turtle-операції; ефект — у можливості показати джерело операції, а не у faithfulness.",
        "4. **Виправлення формулювання ризику (70% → по місяцях)** не зачіпає жодного з наборів: питань про цей ризик там немає. Його ефект варто міряти окремим питанням у наступному прогоні.",
        "",
        "## Як це підтримувати",
        "",
        "| Що | Власник | Періодичність | Поріг / алерт |",
        "|---|---|---|---|",
        "| профіль якості (`quality/profile.py`) | власник сховища | раз на місяць і після імпорту виписки | будь-яка метрика нижче порога з `metrics.json` |",
        "| gate (`quality/gate.py`, CI `quality.yml`) | автоматично | кожен push / PR | ≥ 1 порушення → зміна блокується |",
        "| дедуплікація | власник сховища | після додавання контрагентів | поріг підбирають лише на dev; пари в смузі 0.30–0.70 — суддя, далі людина |",
        "| суперечності | власник сховища | раз на квартал | частка оренди в описі ризику розходиться з перерахунком > 10 в. п. |",
        "| provenance | автоматично (gate) | кожен push | у RDF з'явилась операція без prov:wasDerivedFrom |",
        "| безготівкові витрати без контрагента | власник сховища | раз на місяць | частка нижче 0.95 |",
        "",
        "Аліаси нижче порога автоматично не зливаються: вони лишаються окремими й чекають людину. Рішення судді — порада, яку власник може скасувати через unmerge.",
        "",
    ]
    (ROOT / "quality" / "after_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"prov_after={prov_after:.3f} clusters rule={after_rule} judge={after_judge} rag_probe={ {k: round(v['context_recall'], 2) for k, v in summary.items()} }")


if __name__ == "__main__":
    main()
