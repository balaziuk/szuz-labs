MATCH (o:Expense)-[:IN_CATEGORY]->(:Category)-[:SUBCATEGORY_OF*0..2]->(g:Category)
WHERE (g)-[:SUBCATEGORY_OF]->(:Category {id: 'Cat_Expenses'})
WITH g.name AS expenseGroup, count(o) AS operations, sum(o.amount) AS total
WITH collect({g: expenseGroup, n: operations, t: total}) AS rows, sum(total) AS grand
UNWIND rows AS r
RETURN r.g AS expenseGroup, r.n AS operations, r.t AS total,
       round(100.0 * r.t / grand, 2) AS percent
ORDER BY total DESC;
