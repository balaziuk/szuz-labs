import re
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent


def driver():
    cfg = dotenv_values(ROOT / ".env")
    return GraphDatabase.driver(cfg["NEO4J_URI"], auth=(cfg["NEO4J_USER"], cfg["NEO4J_PASSWORD"]))


def split_statements(text):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return [s.strip() for s in re.split(r";\s*$", "\n".join(lines), flags=re.M) if s.strip()]


def run_file(session, path):
    for stmt in split_statements(Path(path).read_text(encoding="utf-8")):
        t0 = time.perf_counter()
        summary = session.run(stmt).consume()
        c = summary.counters
        print(f"[{(time.perf_counter() - t0) * 1000:7.1f} ms] "
              f"+nodes {c.nodes_created} +rels {c.relationships_created} "
              f"+labels {c.labels_added} props {c.properties_set} "
              f"+constraints {c.constraints_added} +indexes {c.indexes_added} | "
              f"{stmt.splitlines()[0][:70]}")


if __name__ == "__main__":
    with driver() as d, d.session() as s:
        for f in sys.argv[1:]:
            print(f"=== {f}")
            run_file(s, f)
