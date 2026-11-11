"""Генератор вітрини фінансових операцій.

Той самий процес, що в ЛР9 (рахунки, категорії, контрагенти, місячний шаблон
операцій із build_data.py), розгорнутий на 2023-01 … 2026-10, щоб у факті було
≥ 1000 рядків. Seed = 42. Усі суми в гривнях.

Місячний ліміт категорії збігається з планом ЛР9: оренда 15000, комунальні 4000,
харчування 8000, транспорт 2000, зв'язок 300, здоров'я 1000, освіта 1500
(разом 31800, як Budget_Apr2026 … Budget_Aug2026).
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
FIRST = date(2023, 1, 1)
LAST = date(2026, 10, 31)
IRI_NS = "http://example.org/financial-operations#"
LAB9 = Path(__file__).resolve().parents[2] / "9" / "data"

PARENT = {
    "Cat_Housing": "Cat_Expenses",
    "Cat_Daily": "Cat_Expenses",
    "Cat_Services": "Cat_Expenses",
    "Cat_Salary": "Cat_Income",
    "Cat_Freelance": "Cat_Income",
    "Cat_Interest": "Cat_Income",
    "Cat_Rent": "Cat_Housing",
    "Cat_Utilities": "Cat_Housing",
    "Cat_Food": "Cat_Daily",
    "Cat_Transport": "Cat_Daily",
    "Cat_Telecom": "Cat_Services",
    "Cat_Health": "Cat_Services",
    "Cat_Education": "Cat_Services",
}

BUDGET = {
    "Cat_Rent": 15000, "Cat_Utilities": 4000, "Cat_Food": 8000, "Cat_Transport": 2000,
    "Cat_Telecom": 300, "Cat_Health": 1000, "Cat_Education": 1500,
}

UTIL = {1: 4800, 2: 4600, 3: 4000, 4: 4200, 5: 3100, 6: 2400,
        7: 2300, 8: 2500, 9: 2800, 10: 3500, 11: 4000, 12: 4700}

CUR = "Acc_UA123456789"
SAV = "Acc_Savings_UA987654321"


def read_csv(name):
    with open(LAB9 / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def class_id(category_id):
    seen = set()
    cur = category_id
    while cur in PARENT and cur not in seen:
        seen.add(cur)
        cur = PARENT[cur]
    return cur


def month_ops(rng, year, month):
    ops = [
        ("Income", 30000, 1, CUR, "Cp_Employer", "Cat_Salary", "зарплата"),
        ("Expense", 15000, 2, CUR, "Cp_Orendodavets", "Cat_Rent", "оренда"),
        ("Transfer", 3000, 3, CUR, "Cp_Cash", "Cat_SavingsTransfer", "переказ на накопичувальний"),
        ("Expense", 250, 5, CUR, "Cp_Kyivstar", "Cat_Telecom", "мобільний зв'язок та інтернет"),
        ("Income", rng.choice([160, 175, 190, 205]), 28, SAV, "Cp_PrivatBank", "Cat_Interest",
         "відсотки за депозитом"),
        ("Expense", UTIL[month], 10, CUR, "Cp_Utility", "Cat_Utilities", "комунальні послуги"),
    ]
    for _ in range(rng.choice([1, 2])):
        cp = rng.choice(["Cp_FreelanceClient", "Cp_DigitalStudio"])
        ops.append(("Income", rng.choice([6000, 8000, 9500, 12000, 15000]), rng.randint(6, 25),
                    CUR, cp, "Cat_Freelance", "оплата фриланс-проєкту"))
    for _ in range(rng.randint(12, 15)):
        cp = rng.choice(["Cp_Silpo", "Cp_ATB", "Cp_Silpo", "Cp_Cash"])
        ops.append(("Expense", rng.randrange(300, 1800, 10), rng.randint(1, 28), CUR, cp,
                    "Cat_Food", "продукти" if cp != "Cp_Cash" else "продукти (готівка)"))
    for _ in range(rng.randint(6, 8)):
        cp = rng.choice(["Cp_Uklon", "Cp_Uklon", "Cp_Cash"])
        ops.append(("Expense", rng.randrange(80, 450, 5), rng.randint(1, 28), CUR, cp,
                    "Cat_Transport", "таксі" if cp != "Cp_Cash" else "громадський транспорт (готівка)"))
    for _ in range(rng.choice([0, 1, 2])):
        ops.append(("Expense", rng.randrange(200, 1500, 10), rng.randint(1, 28), CUR, "Cp_Apteka",
                    "Cat_Health", "ліки"))
    if rng.random() < 0.6:
        ops.append(("Expense", rng.choice([1200, 1800, 2500]), rng.randint(10, 20), CUR, "Cp_Prometheus",
                    "Cat_Education", "онлайн-курс"))
    return ops


def counterparty_rows(cps):
    rows = [{
        "counterparty_id": "Cp_Cash", "counterparty_name": "Готівка (без контрагента)",
        "counterparty_type": "Unknown", "edrpou": "", "valid_from": FIRST, "valid_to": None,
        "is_current": True,
    }]
    for c in cps:
        if c["id"] == "Cp_DigitalStudio":
            rows.append({
                "counterparty_id": c["id"], "counterparty_name": c["name"],
                "counterparty_type": "Supplier", "edrpou": c["edrpou"],
                "valid_from": FIRST, "valid_to": date(2024, 12, 31), "is_current": False,
            })
            rows.append({
                "counterparty_id": c["id"], "counterparty_name": c["name"],
                "counterparty_type": "Client", "edrpou": c["edrpou"],
                "valid_from": date(2025, 1, 1), "valid_to": None, "is_current": True,
            })
        else:
            rows.append({
                "counterparty_id": c["id"], "counterparty_name": c["name"],
                "counterparty_type": c["type"], "edrpou": c["edrpou"],
                "valid_from": FIRST, "valid_to": None, "is_current": True,
            })
    for i, r in enumerate(rows, start=1):
        r["counterparty_sk"] = i
    return rows


def pick_counterparty(rows, cp_id, op_date):
    for r in rows:
        if r["counterparty_id"] != cp_id:
            continue
        if r["valid_from"] <= op_date and (r["valid_to"] is None or op_date <= r["valid_to"]):
            return r["counterparty_sk"]
    raise KeyError(cp_id)


def build():
    rng = random.Random(SEED)
    accounts = read_csv("accounts.csv")
    categories = read_csv("categories.csv")
    cps = read_csv("counterparties.csv")
    sources = read_csv("sources.csv")
    names = {c["id"]: c["name"] for c in categories}

    dim_account = [{
        "account_sk": i, "account_id": a["id"], "account_number": a["accountNumber"],
        "account_type": a["type"], "currency": a["currency"], "snapshot_balance": float(a["balance"]),
    } for i, a in enumerate(accounts, start=1)]
    acc_sk = {a["account_id"]: a["account_sk"] for a in dim_account}

    dim_category = []
    for i, c in enumerate(categories, start=1):
        root = class_id(c["id"])
        parent = PARENT.get(c["id"])
        dim_category.append({
            "category_sk": i, "category_id": c["id"], "category_name": c["name"], "kind": c["kind"],
            "parent_id": parent or "", "parent_name": names.get(parent, ""),
            "class_id": root, "class_name": names[root],
            "iri": IRI_NS + c["id"], "budget_limit_uah": BUDGET.get(c["id"]),
        })
    cat_sk = {c["category_id"]: c["category_sk"] for c in dim_category}

    dim_cp = counterparty_rows(cps)
    dim_source = [{
        "source_sk": i, "source_id": s["id"], "source_name": s["name"], "source_kind": s["kind"],
    } for i, s in enumerate(sources, start=1)]
    src_sk = {s["source_id"]: s["source_sk"] for s in dim_source}

    dim_date, date_sk = [], {}
    d = FIRST
    while d <= LAST:
        sk = d.year * 10000 + d.month * 100 + d.day
        dim_date.append({
            "date_sk": sk, "full_date": d, "year": d.year, "quarter": (d.month - 1) // 3 + 1,
            "month": d.month, "month_key": f"{d.year:04d}-{d.month:02d}", "day": d.day,
        })
        date_sk[d] = sk
        d += timedelta(days=1)

    facts = []
    seq = 1
    y, m = FIRST.year, FIRST.month
    while (y, m) <= (LAST.year, LAST.month):
        for kind, amount, day, acc, cp, cat, desc in month_ops(rng, y, m):
            op_date = date(y, m, day)
            src = "Src_ManualEntry" if cp == "Cp_Cash" else "Src_BankExport2026"
            facts.append({
                "operation_id": f"Op_G{seq:05d}", "kind": kind, "amount": float(amount),
                "description": desc, "date_sk": date_sk[op_date], "account_sk": acc_sk[acc],
                "category_sk": cat_sk[cat], "counterparty_sk": pick_counterparty(dim_cp, cp, op_date),
                "source_sk": src_sk[src],
            })
            seq += 1
        m += 1
        if m == 13:
            y, m = y + 1, 1

    return {
        "dim_date": dim_date, "dim_account": dim_account, "dim_category": dim_category,
        "dim_counterparty": dim_cp, "dim_source": dim_source, "fact_operation": facts,
        "seed": SEED, "n_facts": len(facts),
    }
