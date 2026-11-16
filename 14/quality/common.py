"""Читання сховища ЛР8–9. Шляхи відносні до szuz-labs."""

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABS = ROOT.parent
CSV_DIR = LABS / "9" / "data"
RDF_PATH = LABS / "8" / "data.ttl"
AS_OF = "2026-11-03"


def read_csv(name):
    with (CSV_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def operations():
    return read_csv("operations.csv")


def relationships():
    return read_csv("relationships.csv")


def edges_by_start():
    grouped = defaultdict(list)
    for row in relationships():
        grouped[row["start"]].append(row)
    return grouped


def load_rdf():
    from rdflib import Graph

    graph = Graph()
    graph.parse(RDF_PATH, format="turtle")
    return graph
