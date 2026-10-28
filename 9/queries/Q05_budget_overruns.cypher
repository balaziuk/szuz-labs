MATCH (b:Budget)-[inc:INCLUDES]->(c:Category)
WHERE inc.plannedAmount IS NOT NULL
OPTIONAL MATCH (o:Expense)-[:IN_CATEGORY]->(c)
WHERE substring(toString(o.date), 0, 7) = b.month
WITH b, c, inc.plannedAmount AS planned, coalesce(sum(o.amount), 0) AS actual
WHERE actual > planned
RETURN b.period AS budget, c.name AS category, planned, actual, actual - planned AS overrun
ORDER BY b.month, overrun DESC;
