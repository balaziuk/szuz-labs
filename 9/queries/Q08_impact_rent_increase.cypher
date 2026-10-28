MATCH (cp:Counterparty {id: 'Cp_Orendodavets'})<-[:WITH_COUNTERPARTY]-(o:Operation)
      -[:IN_CATEGORY]->(c:Category)<-[:INCLUDES]-(b:Budget)<-[:SUMMARIZES]-(r:Report)
WHERE substring(toString(o.date), 0, 7) = b.month
WITH b, c, r, count(DISTINCT o) AS operations, sum(o.amount) AS rentPaid
RETURN b.month AS month, c.name AS category, b.period AS budget, r.id AS report,
       operations, rentPaid, round(100.0 * rentPaid / r.totalExpenses, 1) AS shareOfMonthExpenses
ORDER BY month;
