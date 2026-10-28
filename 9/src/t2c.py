import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

from neo4j import READ_ACCESS
from neo4j.graph import Node
from neo4j.exceptions import Neo4jError

from run_cypher import ROOT, driver

GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
SEED = 42
ROW_LIMIT = 100
WRITE_CLAUSES = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b|CALL\s+(dbms|db\.create|gds|apoc)",
    re.I)

PROMPTS = {
    "v1": """Ти — експерт з Cypher (Neo4j 5). Перетвори питання українською на ОДИН запит Cypher
для графа зі схемою нижче. Поверни лише запит у блоці ```cypher```.

{schema}

Питання: {question}""",
    "v2": """Ти — експерт з Cypher (Neo4j 5). Перетвори питання українською на ОДИН запит Cypher
лише для читання. Поверни тільки запит у блоці ```cypher```, без пояснень.

{schema}

{values}

Правила:
1. Використовуй ЛИШЕ мітки, типи зв'язків і властивості зі схеми; напрямок зв'язків — як у схемі.
2. Значення властивостей українською (назви категорій, контрагентів, рівні ризику) пиши точно так,
   як у прикладах значень; рівні ризику: 'високий', 'середній', 'низький'.
3. Тип операції визначай мітками :Income, :Expense, :Transfer (або o.kind).
4. Дата операції — тип date: фільтруй як date('2026-07-01') <= o.date < date('2026-08-01').
   Бюджети й звіти мають властивість month у форматі 'YYYY-MM'.
5. Контрагент типу постачальника: c.type = 'Supplier'; джерела: Src_BankExport2026, Src_ManualEntry,
   Src_BudgetPlan2026, Src_RiskAnalysis.
6. Значення фільтрів (id, type, level, kind, month) бери ЛИШЕ з наведених вище реальних значень;
   не перекладай і не вигадуй їх. Конкретний вузол (ризик, бюджет, джерело) шукай за його id.
7. Повертай потрібні властивості (наприклад r.id, b.period), а не цілі вузли.
8. Не додавай зайвих стовпців і фільтрів, яких немає в питанні.

Питання: {question}""",
}


def schema_text(s):
    nodes = s.run("""
        CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName
        WITH nodeLabels[0] AS label, collect(DISTINCT propertyName) AS props
        WHERE NOT label IN ['Income', 'Expense', 'Transfer']
        RETURN label, props ORDER BY label""").data()
    rels = s.run("""
        MATCH (a)-[r]->(b)
        WITH DISTINCT [l IN labels(a) WHERE NOT l IN ['Income','Expense','Transfer']][0] AS a,
             type(r) AS t, labels(b)[0] AS b
        RETURN a, t, b ORDER BY t""").data()
    lines = ["Схема графа (Neo4j):", "Вузли:"]
    for n in nodes:
        props = [p for p in n["props"] if p not in ("pagerank", "community")]
        lines.append(f"  (:{n['label']} {{{', '.join(sorted(props))}}})")
    lines.append("  Операції мають додаткову мітку :Income, :Expense або :Transfer.")
    lines.append("Зв'язки (усі мають властивості source, confidence, validFrom; INCLUDES ще plannedAmount):")
    for r in rels:
        lines.append(f"  (:{r['a']})-[:{r['t']}]->(:{r['b']})")
    cats = s.run("MATCH (c:Category) RETURN collect(c.name) AS v").single()["v"]
    cps = s.run("MATCH (c:Counterparty) RETURN collect(c.name) AS v").single()["v"]
    lines.append("Приклади значень: Category.name = " + ", ".join(cats))
    lines.append("Counterparty.name = " + ", ".join(cps))
    return "\n".join(lines)


def value_examples(s):
    q = {
        "Risk (id: type, level)": "MATCH (n:Risk) RETURN n.id + ': ' + n.type + ', ' + n.level AS v ORDER BY v",
        "Source.id": "MATCH (n:Source) RETURN n.id + ' (' + n.name + ')' AS v ORDER BY v",
        "Budget.month / period": "MATCH (n:Budget) RETURN n.month + ' = ' + n.period AS v ORDER BY v",
        "Account.type": "MATCH (n:Account) RETURN DISTINCT n.type AS v",
        "Counterparty.type": "MATCH (n:Counterparty) RETURN DISTINCT n.type AS v",
        "Category.kind": "MATCH (n:Category) RETURN DISTINCT n.kind AS v",
        "Operation.kind": "MATCH (n:Operation) RETURN DISTINCT n.kind AS v",
    }
    lines = ["Реальні значення властивостей:"]
    for title, cypher in q.items():
        lines.append(f"  {title}: " + "; ".join(r["v"] for r in s.run(cypher)))
    return "\n".join(lines)


def schema_sets(s):
    labels = {r["l"] for r in s.run("CALL db.labels() YIELD label RETURN label AS l")}
    rels = {r["t"] for r in s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType AS t")}
    props = {r["p"] for r in s.run("CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey AS p")}
    return labels, rels, props


def api_key():
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY / GEMINI_API_KEY не задано")
    return key.strip().strip('"')


def model_name():
    return GROQ_MODEL if api_key().startswith("gsk_") else GEMINI_MODEL


def call_llm(prompt):
    key = api_key()
    if key.startswith("gsk_"):
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {"model": GROQ_MODEL, "temperature": TEMPERATURE, "seed": SEED,
                "messages": [{"role": "user", "content": prompt}]}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                   "User-Agent": "lab9-t2c/1.0"}
        pick = lambda d: d["choices"][0]["message"]["content"]
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": TEMPERATURE, "seed": SEED}}
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
        pick = lambda d: d["candidates"][0]["content"]["parts"][0]["text"]
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return pick(json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from None


def extract_query(text):
    m = re.search(r"```(?:cypher)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";")


def check_schema(q, labels, rels, props):
    q_clean = re.sub(r"'[^']*'|\"[^\"]*\"", "''", q)
    used_labels = set(re.findall(r"\(\s*\w*\s*:\s*(\w+)", q_clean)) | set(re.findall(r"\w+\s*:\s*(\w+)\s*\)", q_clean))
    used_labels |= set(re.findall(r"\bWHERE\s+\w+:(\w+)", q_clean))
    used_rels = set(re.findall(r"\[\s*\w*\s*:\s*([\w|:]+)", q_clean))
    used_rels = {t for grp in used_rels for t in re.split(r"[|:]", grp) if t}
    used_props = set(re.findall(r"\.(\w+)", q_clean)) | set(re.findall(r"\{\s*(\w+)\s*:", q_clean))
    return sorted((used_labels - labels) | (used_rels - rels) | ({p for p in used_props if p.islower() or p[0].islower()} - props))


def ensure_limit(q):
    return q if re.search(r"\bLIMIT\s+\d+\s*$", q, re.I) else f"{q}\nLIMIT {ROW_LIMIT}"


def expand(row):
    out = []
    for v in row:
        if isinstance(v, Node):
            out += [v[k] for k in sorted(v.keys()) if k not in ("pagerank", "community")]
        else:
            out.append(v)
    return out


def run_read(d, q):
    def work(tx):
        return [expand(r.values()) for r in tx.run(q)]
    with d.session(default_access_mode=READ_ACCESS) as s:
        return s.execute_read(work)


def norm(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, int) and not isinstance(v, bool):
        return round(float(v), 2)
    return str(v)


def same_result(gold_rows, rows):
    if len(gold_rows) != len(rows):
        return False
    if not gold_rows:
        return True
    if len({len(r) for r in rows}) > 1:
        return False
    gcols = [sorted(map(norm, c), key=str) for c in zip(*gold_rows)]
    rcols = [sorted(map(norm, c), key=str) for c in zip(*rows)]
    return all(gc in rcols for gc in gcols)


def evaluate(d, it, q, labels, rels, props):
    rec = {"id": it["id"], "level": it["level"], "question": it["question"], "generated": q,
           "gold": it["gold"], "read_only": not WRITE_CLAUSES.search(q)}
    try:
        with d.session() as s:
            plan = s.run("EXPLAIN " + q).consume()
        rec["syntax_ok"] = True
        rec["read_only"] = rec["read_only"] and plan.query_type == "r"
    except Neo4jError as e:
        rec["syntax_ok"], rec["error"] = False, e.message.splitlines()[0]
    rec["unknown_schema"] = check_schema(q, labels, rels, props)
    rec["schema_only"] = not rec["unknown_schema"]
    rec["correct"] = False
    if rec["syntax_ok"] and rec["read_only"]:
        try:
            rows = run_read(d, ensure_limit(q))
            gold = run_read(d, it["gold"])
            rec["rows"] = len(rows)
            rec["correct"] = same_result(gold, rows)
        except Neo4jError as e:
            rec["error"] = e.message.splitlines()[0]
    return rec


def reevaluate(version):
    items = {json.loads(ln)["id"]: json.loads(ln) for ln in
             (ROOT / "tests" / "t2c_gold.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()}
    path = ROOT / "tests" / f"t2c_{version}.json"
    old = json.loads(path.read_text(encoding="utf-8"))
    with driver() as d:
        with d.session() as s:
            labels, rels, props = schema_sets(s)
        results = []
        for r in old["results"]:
            rec = evaluate(d, items[r["id"]], r["generated"], labels, rels, props)
            rec["llm_ms"] = r.get("llm_ms")
            results.append(rec)
            print(f"{rec['id']} correct={rec['correct']}")
    finish(version, results, old["model"])


def finish(version, results, model):
    n = len(results)
    metrics = {k: round(sum(r[k] for r in results) / n, 3)
               for k in ("syntax_ok", "schema_only", "read_only", "correct")}
    metrics["n"] = n
    out = {"version": version, "model": model, "metrics": metrics, "results": results}
    (ROOT / "tests" / f"t2c_{version}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    with open(ROOT / "tests" / "t2c.jsonl", "w", encoding="utf-8") as f:
        for v in ("v1", "v2"):
            p = ROOT / "tests" / f"t2c_{v}.json"
            if p.exists():
                for r in json.loads(p.read_text(encoding="utf-8"))["results"]:
                    f.write(json.dumps({"prompt_version": v, **r}, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))


def main(version):
    items = [json.loads(ln) for ln in (ROOT / "tests" / "t2c_gold.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    log_dir = ROOT / "llm_log"
    log_dir.mkdir(exist_ok=True)
    results = []
    with driver() as d:
        with d.session() as s:
            schema = schema_text(s)
            values = value_examples(s)
            labels, rels, props = schema_sets(s)
        for it in items:
            prompt = PROMPTS[version].format(schema=schema, values=values, question=it["question"])
            t0 = time.perf_counter()
            raw = call_llm(prompt)
            llm_ms = round((time.perf_counter() - t0) * 1000)
            q = extract_query(raw)
            rec = evaluate(d, it, q, labels, rels, props)
            rec["llm_ms"] = llm_ms
            results.append(rec)
            print(f"{it['id']} syntax={rec['syntax_ok']} schema={rec['schema_only']} "
                  f"ro={rec['read_only']} correct={rec['correct']}")
            with open(log_dir / f"t2c_{version}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "model": model_name(), "temperature": TEMPERATURE, "seed": SEED, "prompt_version": version,
                    "question_id": it["id"], "prompt": prompt, "raw_output": raw,
                    "decision": "accepted" if rec["correct"] else "rejected",
                }, ensure_ascii=False) + "\n")
            time.sleep(3)

    finish(version, results, model_name())


if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else "v1"
    reevaluate(ver) if "--reeval" in sys.argv else main(ver)
