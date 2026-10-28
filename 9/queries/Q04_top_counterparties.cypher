MATCH (o:Expense)
WITH sum(o.amount) AS allExpenses
MATCH (o:Expense)-[:WITH_COUNTERPARTY]->(cp:Counterparty)
WITH cp, allExpenses, count(o) AS operations, sum(o.amount) AS total
RETURN cp.name AS counterparty, operations, total,
       round(100.0 * total / allExpenses, 2) AS percentOfExpenses
ORDER BY total DESC
LIMIT 5;
