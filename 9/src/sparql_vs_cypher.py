import json
import re
import statistics
import time
import urllib.parse
import urllib.request

from run_cypher import ROOT, driver

LAB8 = ROOT.parent / "8" / "queries.rq"
FUSEKI = "http://localhost:3030/fin/sparql"

CYPHER = {
    "Q1": """MATCH (o:Expense)-[:IN_CATEGORY]->(c:Category)
WHERE date('2026-09-01') <= o.date < date('2026-10-01')
RETURN o.id AS op, o.amount AS amount, o.date AS date, c.name AS category
ORDER BY o.date""",
    "Q2": """MATCH (o:Operation)
WHERE date('2026-09-01') <= o.date < date('2026-11-01')
OPTIONAL MATCH (o)-[:WITH_COUNTERPARTY]->(cp:Counterparty)
RETURN o.id AS op, o.amount AS amount, cp.name AS counterpartyName
ORDER BY o.id""",
    "Q3": """MATCH (o:Expense)-[:IN_CATEGORY]->(c:Category)
WHERE date('2026-09-01') <= o.date < date('2026-11-01')
WITH c.name AS category, sum(o.amount) AS catSum
WITH collect({c: category, s: catSum}) AS rows, sum(catSum) AS total
UNWIND rows AS r
RETURN r.c AS category, r.s AS catSum, 100.0 * r.s / total AS percentOfTotal
ORDER BY catSum DESC""",
    "Q4": """MATCH (b:Budget)
WHERE b.actual > b.planned
RETURN b.id AS budget, b.period AS period, b.planned AS planned,
       b.actual AS actual, b.deviation AS deviation""",
    "Q5": """RETURN EXISTS { MATCH (b:Budget) WHERE b.actual > b.planned } AS answer""",
}

QUESTIONS = {
    "Q1": "Які витрати здійснено у вересні 2026?",
    "Q2": "Які операції мають контрагента, а які — ні?",
    "Q3": "Яку частку витрат становить кожна категорія?",
    "Q4": "Які бюджети перевищено і на скільки?",
    "Q5": "Чи перевищено хоча б один бюджет?",
}


def sparql_blocks():
    text = LAB8.read_text(encoding="utf-8")
    prefixes = "\n".join(ln for ln in text.splitlines() if ln.startswith("PREFIX"))
    return {q: prefixes + "\n" + m.strip()
            for q, m in re.findall(r"# BEGIN (Q\d)\n(.*?)# END \1", text, re.S)}


def sparql(q):
    url = FUSEKI + "?" + urllib.parse.urlencode({"query": q})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def local(v):
    return v.split("#")[-1] if v.startswith("http") else v


def norm_sparql(res):
    if "boolean" in res:
        return [(res["boolean"],)]
    vs = res["head"]["vars"]
    return [tuple(local(b[v]["value"]) if v in b else None for v in vs) for b in res["results"]["bindings"]]


def body_len(q):
    lines = [ln for ln in q.strip().splitlines()
             if ln.strip() and not ln.startswith("PREFIX") and not ln.strip().startswith("#")]
    return len(lines), sum(len(ln.strip()) for ln in lines)


def median_ms(fn, n=20):
    fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ts), 2)


def as_key(row):
    out = []
    for v in row:
        if v is None:
            out.append(None)
        elif isinstance(v, bool):
            out.append(v)
        else:
            s = str(v)
            try:
                out.append(round(float(s), 2))
            except ValueError:
                out.append(s[:10] if re.match(r"\d{4}-\d\d-\d\dT", s) else s)
    return tuple(out)


def main():
    sq = sparql_blocks()
    results = {}
    with driver() as d, d.session() as s:
        for q, cy in CYPHER.items():
            sp_rows = norm_sparql(sparql(sq[q]))
            cy_rows = [tuple(r.values()) for r in s.run(cy).data()]
            if q == "Q2":
                sp_rows = [(r[0], r[2], r[3]) for r in sp_rows]
            a = sorted(map(as_key, sp_rows), key=str)
            b = sorted(map(as_key, cy_rows), key=str)
            results[q] = {
                "question": QUESTIONS[q],
                "sparql": sq[q], "cypher": cy,
                "sparql_rows": [list(r) for r in sp_rows], "cypher_rows": [list(map(str, r)) for r in cy_rows],
                "match": a == b,
                "sparql_len": body_len(sq[q]), "cypher_len": body_len(cy),
                "sparql_ms": median_ms(lambda: sparql(sq[q])),
                "cypher_ms": median_ms(lambda: s.run(cy).consume()),
            }
            r = results[q]
            print(f"{q}: match={r['match']} rows={len(sp_rows)}/{len(cy_rows)} "
                  f"len S{r['sparql_len']} C{r['cypher_len']} ms S{r['sparql_ms']} C{r['cypher_ms']}")
            if not r["match"]:
                print("  SPARQL:", a)
                print("  Cypher:", b)
    (ROOT / "docs" / "sparql_vs_cypher_raw.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
