"""Unmerge: розібрати кластер злиття назад на вихідні записи з їхнім provenance.

python quality/unmerge.py privat-talk           — показати кластер і результат розбирання на копії (файл не змінюється)
python quality/unmerge.py privat-talk --apply   — записати результат у quality/merges_unmerged.json
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def unmerge(state, record_id):
    clusters = copy.deepcopy(state["clusters"])
    root = next(key for key, members in clusters.items() if record_id in members)
    members = clusters.pop(root)
    for rid in members:
        clusters[rid] = [rid]
    return root, members, clusters


def main():
    record_id = sys.argv[1] if len(sys.argv) > 1 else "privat-talk"
    state = json.loads((ROOT / "quality" / "merges.json").read_text(encoding="utf-8"))
    singles = len(state["provenance"]) - sum(len(m) for m in state["clusters"].values())
    print(f"merges.json: поріг {state['threshold']}, кластерів злиття {len(state['clusters'])}, записів {len(state['provenance'])}")
    root, members, clusters = unmerge(state, record_id)
    print(f"кластер {root}:")
    for rid in members:
        prov = state["provenance"][rid]
        print(f"  {rid:<14} «{prov['name']}»  ЄДРПОУ {prov['edrpou'] or '—'}")
    print(f"unmerge {record_id}: кластер {root} розібрано на {len(members)} окремі записи")
    print(f"кластерів злиття: {len(state['clusters'])} -> {len(state['clusters']) - 1}; "
          f"канонічних сутностей: {len(state['clusters']) + singles} -> {len(state['clusters']) - 1 + singles + len(members)}")
    print("provenance кожного запису збережено: назва й код повертаються без змін")
    if "--apply" in sys.argv:
        out = {**state, "clusters": {k: v for k, v in clusters.items() if len(v) > 1}, "unmerged": {"root": root, "records": members}}
        path = ROOT / "quality" / "merges_unmerged.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"записано {path.name}; робочий merges.json не змінено")


if __name__ == "__main__":
    main()
