MATCH (cp:Counterparty {id: 'Cp_FreelanceClient'}), (b:Budget {id: 'Budget_Oct2026'})
MATCH p = shortestPath((cp)-[*..6]-(b))
RETURN length(p) AS hops,
       [n IN nodes(p) | coalesce(n.name, n.id)] AS path,
       [r IN relationships(p) | type(r)] AS relTypes;
