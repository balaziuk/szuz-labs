MATCH (o:Operation)-[d:DERIVED_FROM]->(s:Source)
OPTIONAL MATCH (o)-[:WITH_COUNTERPARTY]->(cp:Counterparty)
WITH o, d, s, cp
WHERE cp IS NULL
RETURN s.name AS source, d.confidence AS confidence, o.kind AS kind,
       count(o) AS operations, sum(o.amount) AS total
ORDER BY operations DESC;
