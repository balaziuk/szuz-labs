import json
import time
from pathlib import Path

from run_cypher import ROOT, driver, split_statements


def to_jsonable(v):
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)


def main():
    out = {}
    with driver() as d, d.session() as s:
        for f in sorted((ROOT / "queries").glob("Q*.cypher")):
            text = f.read_text(encoding="utf-8")
            (stmt,) = split_statements(text)
            s.run(stmt).consume()
            t0 = time.perf_counter()
            rows = s.run(stmt).data()
            ms = (time.perf_counter() - t0) * 1000
            out[f.stem] = {"ms": round(ms, 1), "rows": to_jsonable(rows)}
            print(f"=== {f.stem}: {len(rows)} рядків, {ms:.1f} мс")
            for r in rows[:12]:
                print("  ", to_jsonable(r))
    (ROOT / "docs" / "cypher_raw.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
