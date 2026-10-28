MATCH (o:Expense)-[:IN_CATEGORY]->(c:Category)
WHERE date('2026-09-01') <= o.date < date('2026-10-01')
RETURN o.id AS operation, o.amount AS amount, o.date AS date, c.name AS category
ORDER BY o.date;
