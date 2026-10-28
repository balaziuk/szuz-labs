MATCH (o:Expense)-[d:DERIVED_FROM]->(s:Source)
WHERE d.confidence < 1.0 AND o.amount > 1000
MATCH (o)-[:IN_CATEGORY]->(c:Category)
RETURN o.id AS operation, o.amount AS amount, c.name AS category,
       s.name AS source, d.confidence AS confidence, d.validFrom AS validFrom
ORDER BY o.amount DESC;
