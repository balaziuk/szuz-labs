"""Спільні типи витягу для ЛР13. Словник імен береться з реєстру ЛР9."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT.parent / "9" / "data"

ENTITY_TYPES = [
    "Account",
    "Counterparty",
    "Category",
    "Amount",
    "Currency",
    "Period",
    "Risk",
    "Edrpou",
]

RELATION_TYPES = [
    "paidTo",
    "receivedFrom",
    "hasCategory",
    "inPeriod",
    "identifiedBy",
    "hasBudgetLimit",
    "concerns",
]

# Людська інструкція дозволяє ці поверхневі форми. Метод А їх не має в словнику:
# на dev вони не траплялись, тож у правила їх не додавали.
ALIASES = {
    "Приват",
    "ФОПу Іваненку",
    "сільпо",
    "київстар",
    "орендодавцю",
    "їжа",
    "зв'язок",
    "Комуналка",
}

RISKS = [
    ("Ризик концентрації витрат", "Risk_RentConcentration"),
    ("Ризик ліквідності", "Risk_LiquidityOct"),
    ("Валютний ризик", "Risk_CurrencyFreelance"),
    ("Ризик зростання ціни", "Risk_RentIncrease"),
    ("Сезонний ризик", "Risk_UtilitiesSeasonal"),
    ("Ризик залежності доходу", "Risk_IncomeDependency"),
]

LEAF_KINDS = {"IncomeCategory", "ExpenseCategory", "TransferCategory"}


def _rows(name):
    with (REGISTRY / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def accounts():
    return _rows("accounts.csv")


def counterparties():
    return _rows("counterparties.csv")


def categories():
    return [row for row in _rows("categories.csv") if row["kind"] in LEAF_KINDS]


def gazetteer():
    phrases = []
    for row in counterparties():
        phrases.append((row["name"], "Counterparty", row["id"]))
    for row in categories():
        phrases.append((row["name"], "Category", row["id"]))
    for phrase, risk_id in RISKS:
        phrases.append((phrase, "Risk", risk_id))
    phrases.sort(key=lambda item: len(item[0]), reverse=True)
    return phrases
