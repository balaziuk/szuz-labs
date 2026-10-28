MATCH chain = (src:Risk)-[:TRIGGERS*0..2]->(r:Risk)-[:AFFECTS]->(b:Budget)<-[:SUMMARIZES]-(rep:Report)
WHERE NOT ()-[:TRIGGERS]->(src)
RETURN src.id AS rootRisk, src.level AS rootLevel,
       [n IN nodes(chain) WHERE n:Risk | n.id] AS riskChain,
       length(chain) AS depth, b.period AS budget, rep.id AS report
ORDER BY depth DESC, rootRisk, budget;
