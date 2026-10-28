import json
import statistics
import time
from pathlib import Path

from run_cypher import ROOT, driver, split_statements

DATE_QUERY = """
MATCH (o:Operation)
WHERE o.date >= date('2026-07-01') AND o.date < date('2026-08-01') AND o.amount > 1000
RETURN o.id AS operation, o.amount AS amount, o.date AS date
ORDER BY amount DESC
"""


def plan_summary(plan):
    ops, hits = [], 0

    def walk(p):
        nonlocal hits
        hits += p.get("dbHits", 0)
        ops.append(f"{p['operatorType'].split('@')[0]} (rows {p.get('rows', 0)}, dbHits {p.get('dbHits', 0)})")
        for c in p.get("children", []):
            walk(c)

    walk(plan)
    return hits, ops


def profile(s, q):
    summary = s.run("PROFILE " + q).consume()
    return plan_summary(summary.profile)


def timing(s, q, n=30):
    s.run(q).consume()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        s.run(q).consume()
        ts.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ts), 2)


def main():
    out = {}
    with driver() as d, d.session() as s:
        for f in ("gds/01_project.cypher", "gds/02_algorithms.cypher"):
            for st in split_statements((ROOT / f).read_text(encoding="utf-8")):
                rows = s.run(st).data()
                if rows:
                    out.setdefault("gds_calls", []).append(rows[0])

        out["pagerank_top10"] = s.run(
            "MATCH (n) WHERE n.pagerank IS NOT NULL "
            "RETURN labels(n)[0] AS label, coalesce(n.name, n.id) AS node, round(n.pagerank, 4) AS pagerank "
            "ORDER BY pagerank DESC LIMIT 10").data()
        out["communities"] = s.run(
            "MATCH (n) WHERE n.community IS NOT NULL "
            "WITH n.community AS community, collect(n) AS ns "
            "RETURN community, size(ns) AS size, size([x IN ns WHERE x:Operation]) AS operations, "
            "[x IN ns WHERE NOT x:Operation AND NOT x:Report AND NOT x:Budget | coalesce(x.name, x.id)] "
            "AS keyMembers, size([x IN ns WHERE x:Budget OR x:Report]) AS budgetsReports "
            "ORDER BY size DESC").data()

        s.run("DROP INDEX operation_date IF EXISTS").consume()
        hits_b, ops_b = profile(s, DATE_QUERY)
        t_b = timing(s, DATE_QUERY)
        s.run("CREATE INDEX operation_date IF NOT EXISTS FOR (o:Operation) ON (o.date)").consume()
        s.run("CALL db.awaitIndexes(60)").consume()
        hits_a, ops_a = profile(s, DATE_QUERY)
        t_a = timing(s, DATE_QUERY)
        out["profile_date"] = {
            "query": DATE_QUERY.strip(), "rows": s.run(DATE_QUERY).data(),
            "before": {"dbHits": hits_b, "plan": ops_b, "median_ms": t_b},
            "after": {"dbHits": hits_a, "plan": ops_a, "median_ms": t_a},
        }

        q08 = split_statements((ROOT / "queries" / "Q08_impact_rent_increase.cypher").read_text(encoding="utf-8"))[0]
        hits, ops = profile(s, q08)
        out["profile_q08"] = {"query": q08, "dbHits": hits, "plan": ops, "median_ms": timing(s, q08)}

    (ROOT / "docs" / "gds_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                                encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k.startswith("profile")}, ensure_ascii=False,
                     indent=1, default=str))


if __name__ == "__main__":
    main()
