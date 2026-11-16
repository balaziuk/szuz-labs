from rdflib import Graph, Dataset, Namespace, Literal, URIRef, RDF, RDFS, XSD, OWL
from rdflib.namespace import SKOS, FOAF, DCTERMS

FIN = Namespace("http://example.org/financial-operations#")
SRC = Namespace("http://example.org/financial-operations/source#")
PROV = Namespace("http://www.w3.org/ns/prov#")

g = Graph()
g.bind("fin", FIN)
g.bind("rdfs", RDFS)
g.bind("xsd", XSD)
g.bind("skos", SKOS)
g.bind("foaf", FOAF)
g.bind("dcterms", DCTERMS)
g.bind("prov", PROV)
g.bind("owl", OWL)

def L(text):
    return Literal(text, lang="uk")

def S(v):
    return Literal(v, datatype=XSD.string)

def D(v):
    return Literal(v, datatype=XSD.decimal)

def DT(v):
    return Literal(v, datatype=XSD.dateTime)

g.add((FIN.Acc_UA123456789, RDF.type, FIN.CurrentAccount))
g.add((FIN.Acc_UA123456789, FIN.accountNumber, S("UA123456789")))
g.add((FIN.Acc_UA123456789, FIN.currency, S("UAH")))
g.add((FIN.Acc_UA123456789, FIN.balance, D("9000")))

g.add((FIN.Acc_Savings_UA987654321, RDF.type, FIN.SavingsAccount))
g.add((FIN.Acc_Savings_UA987654321, FIN.accountNumber, S("UA987654321")))
g.add((FIN.Acc_Savings_UA987654321, FIN.currency, S("UAH")))
g.add((FIN.Acc_Savings_UA987654321, FIN.balance, D("5000")))

for iri, typ, name, edrpou in [
    (FIN.Cp_Employer, FIN.Client, "ТОВ «Роботодавець»", "87654321"),
    (FIN.Cp_Orendodavets, FIN.Supplier, "ТОВ «Орендодавець»", "12345678"),
    (FIN.Cp_Utility, FIN.Supplier, "АТ «Київські комунальні»", "33445566"),
    (FIN.Cp_FreelanceClient, FIN.Client, "ФОП Іваненко", "99887766"),
]:
    g.add((iri, RDF.type, typ))
    g.add((iri, FIN.counterpartyName, S(name)))
    g.add((iri, FOAF.name, Literal(name, lang="uk")))
    g.add((iri, FIN.edrpouCode, S(edrpou)))

for iri, typ, name, limit in [
    (FIN.Cat_Salary, FIN.IncomeCategory, "Заробітна плата", None),
    (FIN.Cat_Freelance, FIN.IncomeCategory, "Фриланс", None),
    (FIN.Cat_Rent, FIN.ExpenseCategory, "Оренда", "15000"),
    (FIN.Cat_Transport, FIN.ExpenseCategory, "Транспорт", None),
    (FIN.Cat_Food, FIN.ExpenseCategory, "Харчування", None),
    (FIN.Cat_Utilities, FIN.ExpenseCategory, "Комунальні послуги", "4000"),
]:
    g.add((iri, RDF.type, typ))
    g.add((iri, FIN.categoryName, S(name)))
    g.add((iri, SKOS.prefLabel, Literal(name, lang="uk")))
    if limit is not None:
        g.add((iri, FIN.budgetLimit, D(limit)))

ops = [
    (FIN.Op_00124, FIN.Income, "Операція 00124 (зарплата)", FIN.Acc_UA123456789,
     FIN.Cp_Employer, FIN.Cat_Salary, "00124", "2026-09-01T00:00:00", "30000"),
    (FIN.Op_00125, FIN.Expense, "Операція 00125 (оренда)", FIN.Acc_UA123456789,
     FIN.Cp_Orendodavets, FIN.Cat_Rent, "00125", "2026-09-02T00:00:00", "15000"),
    (FIN.Op_00126, FIN.Expense, "Операція 00126 (транспорт)", FIN.Acc_UA123456789,
     None, FIN.Cat_Transport, "00126", "2026-09-03T00:00:00", "2000"),
    (FIN.Op_00127, FIN.Expense, "Операція 00127 (харчування)", FIN.Acc_UA123456789,
     None, FIN.Cat_Food, "00127", "2026-09-05T00:00:00", "4000"),
    (FIN.Op_00128, FIN.Expense, "Операція 00128 (комунальні)", FIN.Acc_UA123456789,
     FIN.Cp_Utility, FIN.Cat_Utilities, "00128", "2026-10-03T00:00:00", "3500"),
    (FIN.Op_00129, FIN.Income, "Операція 00129 (фриланс)", FIN.Acc_UA123456789,
     FIN.Cp_FreelanceClient, FIN.Cat_Freelance, "00129", "2026-10-05T00:00:00", "12000"),
    (FIN.Op_00130, FIN.Expense, "Операція 00130 (оренда)", FIN.Acc_UA123456789,
     FIN.Cp_Orendodavets, FIN.Cat_Rent, "00130", "2026-10-02T00:00:00", "15000"),
    (FIN.Op_00131, FIN.Expense, "Операція 00131 (харчування)", FIN.Acc_UA123456789,
     None, FIN.Cat_Food, "00131", "2026-10-08T00:00:00", "3800"),
]

for iri, typ, label, acc, cp, cat, oid, date, amount in ops:
    g.add((iri, RDF.type, typ))
    g.add((iri, FIN.belongsToAccount, acc))
    if cp is not None:
        g.add((iri, FIN.hasCounterparty, cp))
    g.add((iri, FIN.belongsToCategory, cat))
    g.add((iri, FIN.operationId, S(oid)))
    g.add((iri, FIN.operationDate, DT(date)))
    g.add((iri, DCTERMS.date, DT(date)))
    g.add((iri, FIN.amount, D(amount)))

g.add((FIN.Budget_Sep2026, RDF.type, FIN.Budget))
for cat in (FIN.Cat_Rent, FIN.Cat_Transport, FIN.Cat_Food):
    g.add((FIN.Budget_Sep2026, FIN.includesCategory, cat))
g.add((FIN.Budget_Sep2026, FIN.period, S("вересень 2026")))
g.add((FIN.Budget_Sep2026, FIN.plannedAmount, D("20000")))
g.add((FIN.Budget_Sep2026, FIN.actualAmount, D("21000")))
g.add((FIN.Budget_Sep2026, FIN.deviation, D("1000")))

g.add((FIN.Budget_Oct2026, RDF.type, FIN.Budget))
for cat in (FIN.Cat_Rent, FIN.Cat_Food, FIN.Cat_Utilities):
    g.add((FIN.Budget_Oct2026, FIN.includesCategory, cat))
g.add((FIN.Budget_Oct2026, FIN.period, S("жовтень 2026")))
g.add((FIN.Budget_Oct2026, FIN.plannedAmount, D("25000")))
g.add((FIN.Budget_Oct2026, FIN.actualAmount, D("22300")))
g.add((FIN.Budget_Oct2026, FIN.deviation, D("-2700")))

g.add((FIN.Report_CF_Sep2026, RDF.type, FIN.CashFlowReport))
for op in (FIN.Op_00124, FIN.Op_00125, FIN.Op_00126, FIN.Op_00127):
    g.add((FIN.Report_CF_Sep2026, FIN.aggregates, op))
g.add((FIN.Report_CF_Sep2026, FIN.period, S("вересень 2026")))
g.add((FIN.Report_CF_Sep2026, FIN.totalIncome, D("30000")))
g.add((FIN.Report_CF_Sep2026, FIN.totalExpenses, D("21000")))

g.add((FIN.Report_CF_Oct2026, RDF.type, FIN.CashFlowReport))
for op in (FIN.Op_00128, FIN.Op_00129, FIN.Op_00130, FIN.Op_00131):
    g.add((FIN.Report_CF_Oct2026, FIN.aggregates, op))
g.add((FIN.Report_CF_Oct2026, FIN.period, S("жовтень 2026")))
g.add((FIN.Report_CF_Oct2026, FIN.totalIncome, D("12000")))
g.add((FIN.Report_CF_Oct2026, FIN.totalExpenses, D("22300")))

g.add((FIN.Risk_RentConcentration, RDF.type, FIN.ExpenseConcentrationRisk))
g.add((FIN.Risk_RentConcentration, FIN.relatedToCategory, FIN.Cat_Rent))
g.add((FIN.Risk_RentConcentration, FIN.affectsBudget, FIN.Budget_Sep2026))
g.add((FIN.Risk_RentConcentration, FIN.riskLevel, S("високий")))
g.add((FIN.Risk_RentConcentration, FIN.riskDescription, S("частка оренди понад 70% усіх витрат")))

g.add((FIN.Risk_LiquidityOct, RDF.type, FIN.LiquidityRisk))
g.add((FIN.Risk_LiquidityOct, FIN.affectsBudget, FIN.Budget_Oct2026))
g.add((FIN.Risk_LiquidityOct, FIN.riskLevel, S("середній")))
g.add((FIN.Risk_LiquidityOct, FIN.riskDescription, S("значні витрати на оренду при коливанні доходів")))

g.serialize("data.ttl", format="turtle")
print(f"data.ttl: {len(g)} триплетів")

ds = Dataset()
ds.bind("fin", FIN)
ds.bind("src", SRC)
ds.bind("prov", PROV)
ds.bind("rdfs", RDFS)
ds.bind("xsd", XSD)

ng = URIRef("http://example.org/financial-operations/graph/bank-export-2026")
cg = ds.graph(ng)

cg.add((SRC.BankExport2026, RDF.type, PROV.Entity))
cg.add((SRC.BankExport2026, RDFS.label, L("Експорт банківських операцій 2026")))
cg.add((SRC.BankExport2026, PROV.generatedAtTime, DT("2026-10-15T12:00:00")))
cg.add((SRC.BankExport2026, FIN.period, S("вересень–жовтень 2026")))
cg.add((SRC.BankExport2026, PROV.wasAttributedTo, FIN.Cp_Employer))

for op, *_ in ops:
    cg.add((op, PROV.wasDerivedFrom, SRC.BankExport2026))

ds.serialize("source_graph.trig", format="trig")
print(f"source_graph.trig: іменований граф {ng}, триплетів у графі: {len(cg)}")
