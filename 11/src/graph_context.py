import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB9 = ROOT.parent / "9" / "data"
LAB9_ENV = ROOT.parent / "9" / ".env"
EDGE_LIMIT = 24
OP_LIMIT = 5

SYNONYMS = [
    ("орендодав", "Cp_Orendodavets"),
    ("комунал", "Cat_Utilities"),
    ("харчуван", "Cat_Food"),
    ("продукт", "Cat_Food"),
    ("транспорт", "Cat_Transport"),
    ("зарплат", "Cat_Salary"),
    ("фриланс", "Cat_Freelance"),
    ("відсот", "Cat_Interest"),
    ("депозит", "Cat_Interest"),
    ("київстар", "Cp_Kyivstar"),
    ("зв'язок", "Cat_Telecom"),
    ("інтернет", "Cat_Telecom"),
    ("здоров", "Cat_Health"),
    ("ліки", "Cat_Health"),
    ("освіт", "Cat_Education"),
    ("житл", "Cat_Housing"),
    ("оренд", "Cat_Rent"),
    ("сільпо", "Cp_Silpo"),
    ("приват", "Cp_PrivatBank"),
    ("роботодав", "Cp_Employer"),
    ("іваненко", "Cp_FreelanceClient"),
    ("діджитал", "Cp_DigitalStudio"),
    ("уклон", "Cp_Uklon"),
    ("аптек", "Cp_Apteka"),
    ("прометеус", "Cp_Prometheus"),
    ("накопич", "Acc_Savings_UA987654321"),
    ("поточн", "Acc_UA123456789"),
    ("атб", "Cp_ATB"),
]

QUESTIONS = [
    {"id": "G01", "question": "Який id контрагента, якому платять за оренду?", "expect": ["Cp_Orendodavets"]},
    {"id": "G02", "question": "Який id батьківської категорії статті «Оренда»?", "expect": ["Cat_Housing"]},
    {"id": "G03", "question": "З якого id рахунку надходить зарплата?", "expect": ["Acc_UA123456789"]},
    {"id": "G04", "question": "Які id дочірніх категорій має група «Житло»?", "expect": ["Cat_Rent", "Cat_Utilities"]},
    {"id": "G05", "question": "Який id контрагента комунальних послуг?", "expect": ["Cp_Utility"]},
    {"id": "G06", "question": "Який id джерела в операції оренди?", "expect": ["Src_BankExport2026"]},
    {"id": "G07", "question": "На який id рахунку нараховують відсотки за депозитом?", "expect": ["Acc_Savings_UA987654321"]},
    {"id": "G08", "question": "Який id контрагента ТОВ «Сільпо-Фуд» і який у нього тип?", "expect": ["Cp_Silpo", "Supplier"]},
    {"id": "G09", "question": "Який id категорії є батьком «Харчування»?", "expect": ["Cat_Daily"]},
    {"id": "G10", "question": "Який місячний ліміт категорії Cat_Rent і в якій вона групі?", "expect": ["15000", "Cat_Housing"]},
    {"id": "G11", "question": "Кому ми платимо за оренду квартири?", "expect": ["Орендодавець"], "no_id": True},
    {"id": "G12", "question": "До якої групи витрат належать оренда і комунальні послуги?", "expect": ["Житло"], "no_id": True},
    {"id": "G13", "question": "Який місячний ліміт витрат на комунальні послуги?", "expect": ["4000"], "no_id": True},
    {"id": "G14", "question": "Через якого перевізника ми оплачуємо транспорт?", "expect": ["Уклон"], "no_id": True},
    {"id": "G15", "question": "Який оператор надає нам зв'язок та інтернет?", "expect": ["Київстар"], "no_id": True},
    {"id": "G16", "question": "Хто виплачує нам зарплату?", "expect": ["Роботодавець"], "no_id": True},
]

NODES_CYPHER = """
MATCH (n) WHERE n:Category OR n:Counterparty OR n:Account OR n:Source OR n:Operation
RETURN labels(n) AS labels, properties(n) AS p
"""
EDGES_CYPHER = "MATCH (a)-[r]->(b) RETURN type(r) AS rel, a.id AS a, b.id AS b"
KINDS = ("Category", "Counterparty", "Account", "Source", "Operation")


def read_csv(name):
    with open(LAB9 / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def category_node(id_, name, kind, budget):
    return {"id": id_, "kind": "Category", "name": name, "type": kind, "budget": budget}


def load_csv():
    nodes = {}
    for c in read_csv("categories.csv"):
        nodes[c["id"]] = category_node(c["id"], c["name"], c["kind"], c.get("budgetLimit") or "")
    for c in read_csv("counterparties.csv"):
        nodes[c["id"]] = {"id": c["id"], "kind": "Counterparty", "name": c["name"], "type": c["type"]}
    for a in read_csv("accounts.csv"):
        nodes[a["id"]] = {"id": a["id"], "kind": "Account", "name": a["accountNumber"], "type": a["type"]}
    for s in read_csv("sources.csv"):
        nodes[s["id"]] = {"id": s["id"], "kind": "Source", "name": s["name"], "type": s["kind"]}
    for o in read_csv("operations.csv"):
        nodes[o["id"]] = {"id": o["id"], "kind": "Operation", "name": o["description"],
                          "type": o["kind"], "amount": o["amount"], "date": o["date"]}
    return nodes, [(r["type"], r["start"], r["end"]) for r in read_csv("relationships.csv")]


def node_from_neo4j(labels, p):
    kind = next(k for k in KINDS if k in labels)
    if kind == "Category":
        budget = p.get("budgetLimit")
        return category_node(p["id"], p["name"], p["kind"], "" if budget is None else str(budget))
    if kind == "Counterparty":
        return {"id": p["id"], "kind": kind, "name": p["name"], "type": p["type"]}
    if kind == "Account":
        return {"id": p["id"], "kind": kind, "name": p["accountNumber"], "type": p["type"]}
    if kind == "Source":
        return {"id": p["id"], "kind": kind, "name": p["name"], "type": p["kind"]}
    return {"id": p["id"], "kind": kind, "name": p["description"], "type": p["kind"],
            "amount": str(p["amount"]), "date": str(p["date"])}


def load_neo4j():
    from dotenv import dotenv_values
    from neo4j import READ_ACCESS, GraphDatabase

    cfg = dotenv_values(LAB9_ENV)
    with GraphDatabase.driver(cfg["NEO4J_URI"], auth=(cfg["NEO4J_USER"], cfg["NEO4J_PASSWORD"])) as driver:
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = [node_from_neo4j(r["labels"], r["p"]) for r in session.run(NODES_CYPHER)]
            edges = [(r["rel"], r["a"], r["b"]) for r in session.run(EDGES_CYPHER)]
    return {n["id"]: n for n in nodes}, edges


class Graph:
    def __init__(self, backend=None):
        self.backend = backend or os.environ.get("LAB11_GRAPH", "neo4j")
        self.nodes, edges = load_neo4j() if self.backend == "neo4j" else load_csv()
        known = [e for e in edges if e[1] in self.nodes and e[2] in self.nodes]
        self.edges = sorted(known, key=lambda e: (e[1], e[0], e[2]))
        self.by_name = {n["name"].casefold(): n["id"] for n in self.nodes.values()
                        if n.get("name") and n["kind"] != "Operation"}

    def link(self, question):
        q = question.casefold()
        found = []
        for name, nid in sorted(self.by_name.items(), key=lambda x: -len(x[0])):
            if len(name) >= 4 and name in q and nid not in found:
                found.append(nid)
        for needle, nid in SYNONYMS:
            if needle in q and nid not in found:
                found.append(nid)
        for token in question.replace("«", " ").replace("»", " ").replace("?", " ").split():
            if token in self.nodes and token not in found:
                found.append(token)
        return found[:4]

    def subgraph(self, seeds):
        seen_edges = []
        node_ids = set(seeds)
        ops_per = {}

        def add_edge(edge):
            if edge in seen_edges or len(seen_edges) >= EDGE_LIMIT:
                return
            rel, a, b = edge
            if rel == "IN_CATEGORY" and a.startswith("Op_"):
                cat = b
                ops_per.setdefault(cat, 0)
                if ops_per[cat] >= OP_LIMIT:
                    return
                ops_per[cat] += 1
            seen_edges.append(edge)
            node_ids.add(a)
            node_ids.add(b)

        frontier = list(seeds)
        for _ in range(2):
            nxt = []
            for nid in frontier:
                for edge in self.edges:
                    if nid not in edge[1:]:
                        continue
                    add_edge(edge)
                    other = edge[2] if edge[1] == nid else edge[1]
                    if other not in frontier:
                        nxt.append(other)
                if len(seen_edges) >= EDGE_LIMIT:
                    break
            frontier = nxt
        return node_ids, seen_edges

    def linearize(self, question):
        seeds = self.link(question)
        node_ids, edges = self.subgraph(seeds)
        lines = []
        for nid in sorted(node_ids):
            n = self.nodes.get(nid)
            if not n:
                continue
            extra = " ".join(f"{k}={n[k]}" for k in ("type", "amount", "date", "budget") if n.get(k))
            lines.append(f"[{nid}] {n['kind']} {n['name']} {extra}".rstrip())
        for rel, a, b in edges:
            lines.append(f"[{a}] -{rel}-> [{b}]")
        return seeds, "\n".join(lines), {nid for nid in node_ids}
