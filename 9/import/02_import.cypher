LOAD CSV WITH HEADERS FROM 'file:///sources.csv' AS r
MERGE (n:Source {id: r.id})
SET n.name = r.name, n.kind = r.kind, n.generatedAt = date(r.generatedAt);

LOAD CSV WITH HEADERS FROM 'file:///accounts.csv' AS r
MERGE (n:Account {id: r.id})
SET n.accountNumber = r.accountNumber, n.type = r.type, n.currency = r.currency,
    n.balance = toFloat(r.balance);

LOAD CSV WITH HEADERS FROM 'file:///counterparties.csv' AS r
MERGE (n:Counterparty {id: r.id})
SET n.name = r.name, n.type = r.type, n.edrpou = r.edrpou;

LOAD CSV WITH HEADERS FROM 'file:///categories.csv' AS r
MERGE (n:Category {id: r.id})
SET n.name = r.name, n.kind = r.kind, n.budgetLimit = toFloat(r.budgetLimit);

LOAD CSV WITH HEADERS FROM 'file:///operations.csv' AS r
MERGE (n:Operation {id: r.id})
SET n.kind = r.kind, n.amount = toFloat(r.amount), n.date = date(r.date),
    n.description = r.description, n.currency = r.currency;

MATCH (o:Operation {kind: 'Income'}) SET o:Income;
MATCH (o:Operation {kind: 'Expense'}) SET o:Expense;
MATCH (o:Operation {kind: 'Transfer'}) SET o:Transfer;

LOAD CSV WITH HEADERS FROM 'file:///budgets.csv' AS r
MERGE (n:Budget {id: r.id})
SET n.period = r.period, n.month = r.month, n.planned = toFloat(r.planned),
    n.actual = toFloat(r.actual), n.deviation = toFloat(r.deviation);

LOAD CSV WITH HEADERS FROM 'file:///reports.csv' AS r
MERGE (n:Report {id: r.id})
SET n.period = r.period, n.month = r.month, n.totalIncome = toFloat(r.totalIncome),
    n.totalExpenses = toFloat(r.totalExpenses);

LOAD CSV WITH HEADERS FROM 'file:///risks.csv' AS r
MERGE (n:Risk {id: r.id})
SET n.type = r.type, n.level = r.level, n.description = r.description;

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'FROM_ACCOUNT'
MATCH (a:Operation {id: r.start}), (b:Account {id: r.end})
MERGE (a)-[x:FROM_ACCOUNT]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'TO_ACCOUNT'
MATCH (a:Operation {id: r.start}), (b:Account {id: r.end})
MERGE (a)-[x:TO_ACCOUNT]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'IN_CATEGORY'
MATCH (a:Operation {id: r.start}), (b:Category {id: r.end})
MERGE (a)-[x:IN_CATEGORY]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'WITH_COUNTERPARTY'
MATCH (a:Operation {id: r.start}), (b:Counterparty {id: r.end})
MERGE (a)-[x:WITH_COUNTERPARTY]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'DERIVED_FROM'
MATCH (a {id: r.start}), (b:Source {id: r.end})
MERGE (a)-[x:DERIVED_FROM]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'SUBCATEGORY_OF'
MATCH (a:Category {id: r.start}), (b:Category {id: r.end})
MERGE (a)-[x:SUBCATEGORY_OF]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'INCLUDES'
MATCH (a:Budget {id: r.start}), (b:Category {id: r.end})
MERGE (a)-[x:INCLUDES]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom),
    x.plannedAmount = toFloat(r.plannedAmount);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'SUMMARIZES'
MATCH (a:Report {id: r.start}), (b:Budget {id: r.end})
MERGE (a)-[x:SUMMARIZES]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'AGGREGATES'
MATCH (a:Report {id: r.start}), (b:Operation {id: r.end})
MERGE (a)-[x:AGGREGATES]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'RELATED_TO'
MATCH (a:Risk {id: r.start}), (b:Category {id: r.end})
MERGE (a)-[x:RELATED_TO]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'AFFECTS'
MATCH (a:Risk {id: r.start}), (b:Budget {id: r.end})
MERGE (a)-[x:AFFECTS]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'CONCERNS'
MATCH (a:Risk {id: r.start}), (b:Counterparty {id: r.end})
MERGE (a)-[x:CONCERNS]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS r
WITH r WHERE r.type = 'TRIGGERS'
MATCH (a:Risk {id: r.start}), (b:Risk {id: r.end})
MERGE (a)-[x:TRIGGERS]->(b)
SET x.source = r.source, x.confidence = toFloat(r.confidence), x.validFrom = date(r.validFrom);
