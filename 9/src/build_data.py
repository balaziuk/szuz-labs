import csv
import random
from datetime import date
from pathlib import Path

SEED = 42
DATA = Path(__file__).resolve().parent.parent / "data"

SRC_BANK = "Src_BankExport2026"
SRC_MANUAL = "Src_ManualEntry"
SRC_PLAN = "Src_BudgetPlan2026"
SRC_RISK = "Src_RiskAnalysis"
CONF = {SRC_BANK: 1.0, SRC_MANUAL: 0.85, SRC_PLAN: 1.0, SRC_RISK: 0.7}

SOURCES = [
    (SRC_BANK, "Експорт банківських операцій 2026", "bank_export", "2026-10-15"),
    (SRC_MANUAL, "Ручне введення готівкових витрат", "manual", "2026-10-15"),
    (SRC_PLAN, "Річний фінансовий план 2026", "plan", "2026-03-25"),
    (SRC_RISK, "Аналіз фінансових ризиків (фінменеджер)", "analysis", "2026-10-10"),
]

ACCOUNTS = [
    ("Acc_UA123456789", "UA123456789", "CurrentAccount", "UAH", 9000.0),
    ("Acc_Savings_UA987654321", "UA987654321", "SavingsAccount", "UAH", 5000.0),
]

COUNTERPARTIES = [
    ("Cp_Employer", "ТОВ «Роботодавець»", "Client", "87654321"),
    ("Cp_FreelanceClient", "ФОП Іваненко", "Client", "99887766"),
    ("Cp_DigitalStudio", "ТОВ «Діджитал Студіо»", "Client", "41122334"),
    ("Cp_PrivatBank", "АТ КБ «ПриватБанк»", "Bank", "14360570"),
    ("Cp_Orendodavets", "ТОВ «Орендодавець»", "Supplier", "12345678"),
    ("Cp_Utility", "АТ «Київські комунальні»", "Supplier", "33445566"),
    ("Cp_Kyivstar", "ПрАТ «Київстар»", "Supplier", "21673832"),
    ("Cp_Silpo", "ТОВ «Сільпо-Фуд»", "Supplier", "40720198"),
    ("Cp_ATB", "ТОВ «АТБ-Маркет»", "Supplier", "30487219"),
    ("Cp_Uklon", "ТОВ «Уклон»", "Supplier", "39932340"),
    ("Cp_Apteka", "ТОВ «Аптека АНЦ»", "Supplier", "36151140"),
    ("Cp_Prometheus", "ГО «Прометеус»", "Supplier", "39185340"),
]

CATEGORIES = [
    ("Cat_Income", "Доходи", "IncomeGroup", None, None),
    ("Cat_Expenses", "Витрати", "ExpenseGroup", None, None),
    ("Cat_Housing", "Житло", "ExpenseGroup", "Cat_Expenses", None),
    ("Cat_Daily", "Повсякденні витрати", "ExpenseGroup", "Cat_Expenses", None),
    ("Cat_Services", "Послуги та розвиток", "ExpenseGroup", "Cat_Expenses", None),
    ("Cat_Salary", "Заробітна плата", "IncomeCategory", "Cat_Income", None),
    ("Cat_Freelance", "Фриланс", "IncomeCategory", "Cat_Income", None),
    ("Cat_Interest", "Відсотки за депозитом", "IncomeCategory", "Cat_Income", None),
    ("Cat_Rent", "Оренда", "ExpenseCategory", "Cat_Housing", 15000.0),
    ("Cat_Utilities", "Комунальні послуги", "ExpenseCategory", "Cat_Housing", 4000.0),
    ("Cat_Food", "Харчування", "ExpenseCategory", "Cat_Daily", None),
    ("Cat_Transport", "Транспорт", "ExpenseCategory", "Cat_Daily", None),
    ("Cat_Telecom", "Зв'язок та інтернет", "ExpenseCategory", "Cat_Services", None),
    ("Cat_Health", "Здоров'я", "ExpenseCategory", "Cat_Services", None),
    ("Cat_Education", "Освіта", "ExpenseCategory", "Cat_Services", None),
    ("Cat_SavingsTransfer", "Переказ на накопичення", "TransferCategory", None, None),
]

PLAN = {
    "Cat_Rent": 15000, "Cat_Utilities": 4000, "Cat_Food": 8000, "Cat_Transport": 2000,
    "Cat_Telecom": 300, "Cat_Health": 1000, "Cat_Education": 1500,
}

MONTHS_UK = {4: "квітень", 5: "травень", 6: "червень", 7: "липень", 8: "серпень",
             9: "вересень", 10: "жовтень"}
MONTH_CODE = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct"}

LAB8_OPS = [
    ("00124", "Income", 30000, "2026-09-01", "Cp_Employer", "Cat_Salary", "зарплата"),
    ("00125", "Expense", 15000, "2026-09-02", "Cp_Orendodavets", "Cat_Rent", "оренда"),
    ("00126", "Expense", 2000, "2026-09-03", None, "Cat_Transport", "транспорт"),
    ("00127", "Expense", 4000, "2026-09-05", None, "Cat_Food", "харчування"),
    ("00128", "Expense", 3500, "2026-10-03", "Cp_Utility", "Cat_Utilities", "комунальні"),
    ("00129", "Income", 12000, "2026-10-05", "Cp_FreelanceClient", "Cat_Freelance", "фриланс"),
    ("00130", "Expense", 15000, "2026-10-02", "Cp_Orendodavets", "Cat_Rent", "оренда"),
    ("00131", "Expense", 3800, "2026-10-08", None, "Cat_Food", "харчування"),
]

CUR = "Acc_UA123456789"
SAV = "Acc_Savings_UA987654321"


def synth_month(rng, month):
    ops = [
        ("Income", 30000, 1, CUR, "Cp_Employer", "Cat_Salary", "зарплата", None),
        ("Expense", 15000, 2, CUR, "Cp_Orendodavets", "Cat_Rent", "оренда", None),
        ("Transfer", 3000, 3, CUR, None, "Cat_SavingsTransfer", "переказ на накопичувальний", SAV),
        ("Expense", 250, 5, CUR, "Cp_Kyivstar", "Cat_Telecom", "мобільний зв'язок та інтернет", None),
        ("Income", rng.choice([160, 175, 190, 205]), 28, SAV, "Cp_PrivatBank", "Cat_Interest",
         "відсотки за депозитом", None),
    ]
    util = {4: 4200, 5: 3100, 6: 2400, 7: 2300, 8: 2500}[month]
    ops.append(("Expense", util, 10, CUR, "Cp_Utility", "Cat_Utilities", "комунальні послуги", None))
    for _ in range(rng.choice([1, 1, 2])):
        cp = rng.choice(["Cp_FreelanceClient", "Cp_DigitalStudio"])
        ops.append(("Income", rng.choice([6000, 8000, 9500, 12000, 15000]), rng.randint(6, 25), CUR,
                    cp, "Cat_Freelance", "оплата фриланс-проєкту (USD)", None))
    for _ in range(rng.randint(6, 9)):
        cp = rng.choice(["Cp_Silpo", "Cp_ATB", "Cp_Silpo", None])
        ops.append(("Expense", rng.randrange(300, 1800, 10), rng.randint(1, 28), CUR, cp, "Cat_Food",
                    "продукти" if cp else "продукти (готівка)", None))
    for _ in range(rng.randint(4, 6)):
        cp = rng.choice(["Cp_Uklon", "Cp_Uklon", None])
        ops.append(("Expense", rng.randrange(80, 450, 5), rng.randint(1, 28), CUR, cp, "Cat_Transport",
                    "таксі" if cp else "громадський транспорт (готівка)", None))
    for _ in range(rng.choice([0, 1, 2])):
        ops.append(("Expense", rng.randrange(200, 1500, 10), rng.randint(1, 28), CUR, "Cp_Apteka",
                    "Cat_Health", "ліки", None))
    if rng.random() < 0.6:
        ops.append(("Expense", rng.choice([1200, 1800, 2500]), rng.randint(10, 20), CUR, "Cp_Prometheus",
                    "Cat_Education", "онлайн-курс", None))
    return ops


def main():
    rng = random.Random(SEED)
    DATA.mkdir(exist_ok=True)

    operations, rels = [], []

    def rel(t, a, b, src, valid_from, planned=""):
        rels.append([t, a, b, src, CONF[src], valid_from, planned])

    synth = []
    for m in range(4, 9):
        for k, amount, day, acc, cp, cat, desc, to_acc in synth_month(rng, m):
            synth.append((date(2026, m, day), k, amount, acc, cp, cat, desc, to_acc))
    synth.sort(key=lambda x: (x[0], x[5]))
    for i, (d, k, amount, acc, cp, cat, desc, to_acc) in enumerate(synth, start=1):
        src = SRC_MANUAL if (cp is None and k == "Expense") else SRC_BANK
        operations.append([f"Op_{i:05d}", k, float(amount), d.isoformat(), desc,
                           "USD" if "USD" in desc else "UAH", acc, cp, cat, src, to_acc])
    assert len(operations) < 124, "id синтетичних операцій мають бути меншими за 00124 (ЛР8)"

    for oid, k, amount, d, cp, cat, desc in LAB8_OPS:
        src = SRC_MANUAL if cp is None else SRC_BANK
        operations.append([f"Op_{oid}", k, float(amount), d, desc, "UAH", CUR, cp, cat, src, None])

    for op_id, k, amount, d, desc, cur, acc, cp, cat, src, to_acc in operations:
        rel("FROM_ACCOUNT", op_id, acc, src, d)
        rel("IN_CATEGORY", op_id, cat, src, d)
        rel("DERIVED_FROM", op_id, src, src, d)
        if cp:
            rel("WITH_COUNTERPARTY", op_id, cp, src, d)
        if to_acc:
            rel("TO_ACCOUNT", op_id, to_acc, src, d)

    for cid, _, _, parent, _ in CATEGORIES:
        if parent:
            rel("SUBCATEGORY_OF", cid, parent, SRC_PLAN, "2026-01-01")

    budgets, reports = [], []
    by_month = {}
    for op in operations:
        by_month.setdefault(int(op[3][5:7]), []).append(op)

    lab8_budgets = {
        9: (20000.0, 21000.0, ["Cat_Rent", "Cat_Transport", "Cat_Food"]),
        10: (25000.0, 22300.0, ["Cat_Rent", "Cat_Food", "Cat_Utilities"]),
    }
    for m in range(4, 11):
        code = f"{MONTH_CODE[m]}2026"
        period = f"{MONTHS_UK[m]} 2026"
        b_id, r_id = f"Budget_{code}", f"Report_CF_{code}"
        ops_m = by_month[m]
        income = sum(o[2] for o in ops_m if o[1] == "Income" and o[6] == CUR)
        expenses = sum(o[2] for o in ops_m if o[1] == "Expense")
        if m in lab8_budgets:
            planned, actual, cats = lab8_budgets[m]
            for c in cats:
                rel("INCLUDES", b_id, c, SRC_PLAN, f"2026-{m:02d}-01")
        else:
            planned = float(sum(PLAN.values()))
            actual = float(sum(o[2] for o in ops_m if o[1] == "Expense" and o[8] in PLAN))
            for c, p in PLAN.items():
                rel("INCLUDES", b_id, c, SRC_PLAN, f"2026-{m:02d}-01", p)
        budgets.append([b_id, period, f"2026-{m:02d}", planned, actual, actual - planned])
        rel("DERIVED_FROM", b_id, SRC_PLAN, SRC_PLAN, f"2026-{m:02d}-01")
        reports.append([r_id, period, f"2026-{m:02d}", income, expenses])
        rel("SUMMARIZES", r_id, b_id, SRC_BANK, f"2026-{m:02d}-01")
        for o in ops_m:
            rel("AGGREGATES", r_id, o[0], o[9], o[3])

    risks = [
        ("Risk_RentConcentration", "ExpenseConcentrationRisk", "високий",
         "частка оренди понад 70% усіх витрат"),
        ("Risk_LiquidityOct", "LiquidityRisk", "середній",
         "значні витрати на оренду при коливанні доходів"),
        ("Risk_CurrencyFreelance", "CurrencyRisk", "середній",
         "фриланс-доходи в USD залежать від курсу гривні"),
        ("Risk_IncomeDependency", "IncomeConcentrationRisk", "високий",
         "основний дохід залежить від одного роботодавця"),
        ("Risk_RentIncrease", "PriceRisk", "середній",
         "можливе підвищення орендної плати орендодавцем"),
        ("Risk_UtilitiesSeasonal", "SeasonalRisk", "низький",
         "сезонне зростання комунальних платежів"),
    ]
    for rid, *_ in risks:
        rel("DERIVED_FROM", rid, SRC_RISK, SRC_RISK, "2026-10-10")
    rel("RELATED_TO", "Risk_RentConcentration", "Cat_Rent", SRC_RISK, "2026-04-01")
    for m in range(4, 10):
        rel("AFFECTS", "Risk_RentConcentration", f"Budget_{MONTH_CODE[m]}2026", SRC_RISK, f"2026-{m:02d}-01")
    rel("AFFECTS", "Risk_LiquidityOct", "Budget_Oct2026", SRC_RISK, "2026-10-01")
    rel("RELATED_TO", "Risk_CurrencyFreelance", "Cat_Freelance", SRC_RISK, "2026-04-01")
    rel("CONCERNS", "Risk_CurrencyFreelance", "Cp_FreelanceClient", SRC_RISK, "2026-04-01")
    rel("CONCERNS", "Risk_CurrencyFreelance", "Cp_DigitalStudio", SRC_RISK, "2026-04-01")
    rel("TRIGGERS", "Risk_CurrencyFreelance", "Risk_LiquidityOct", SRC_RISK, "2026-10-01")
    rel("RELATED_TO", "Risk_IncomeDependency", "Cat_Salary", SRC_RISK, "2026-04-01")
    rel("CONCERNS", "Risk_IncomeDependency", "Cp_Employer", SRC_RISK, "2026-04-01")
    rel("TRIGGERS", "Risk_IncomeDependency", "Risk_LiquidityOct", SRC_RISK, "2026-10-01")
    rel("RELATED_TO", "Risk_RentIncrease", "Cat_Rent", SRC_RISK, "2026-07-01")
    rel("CONCERNS", "Risk_RentIncrease", "Cp_Orendodavets", SRC_RISK, "2026-07-01")
    rel("TRIGGERS", "Risk_RentIncrease", "Risk_RentConcentration", SRC_RISK, "2026-07-01")
    rel("RELATED_TO", "Risk_UtilitiesSeasonal", "Cat_Utilities", SRC_RISK, "2026-04-01")
    rel("CONCERNS", "Risk_UtilitiesSeasonal", "Cp_Utility", SRC_RISK, "2026-04-01")
    rel("AFFECTS", "Risk_UtilitiesSeasonal", "Budget_Oct2026", SRC_RISK, "2026-10-01")

    def write(name, header, rows):
        with open(DATA / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("accounts.csv", ["id", "accountNumber", "type", "currency", "balance"], ACCOUNTS)
    write("counterparties.csv", ["id", "name", "type", "edrpou"], COUNTERPARTIES)
    write("categories.csv", ["id", "name", "kind", "budgetLimit"],
          [[c[0], c[1], c[2], c[4] if c[4] is not None else ""] for c in CATEGORIES])
    write("operations.csv", ["id", "kind", "amount", "date", "description", "currency"],
          [o[:6] for o in operations])
    write("budgets.csv", ["id", "period", "month", "planned", "actual", "deviation"], budgets)
    write("reports.csv", ["id", "period", "month", "totalIncome", "totalExpenses"], reports)
    write("risks.csv", ["id", "type", "level", "description"], risks)
    write("sources.csv", ["id", "name", "kind", "generatedAt"], SOURCES)
    write("relationships.csv",
          ["type", "start", "end", "source", "confidence", "validFrom", "plannedAmount"], rels)

    n_nodes = (len(ACCOUNTS) + len(COUNTERPARTIES) + len(CATEGORIES) + len(operations)
               + len(budgets) + len(reports) + len(risks) + len(SOURCES))
    print(f"вузлів: {n_nodes}, зв'язків: {len(rels)}, операцій: {len(operations)}")


if __name__ == "__main__":
    main()
