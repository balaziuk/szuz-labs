CALL gds.graph.drop('finDirected', false) YIELD graphName RETURN graphName;
CALL gds.graph.drop('finUndirected', false) YIELD graphName RETURN graphName;

CALL gds.graph.project(
  'finDirected',
  ['Operation', 'Account', 'Counterparty', 'Category', 'Budget', 'Report', 'Risk'],
  ['FROM_ACCOUNT', 'TO_ACCOUNT', 'IN_CATEGORY', 'WITH_COUNTERPARTY', 'SUBCATEGORY_OF', 'INCLUDES',
   'SUMMARIZES', 'AGGREGATES', 'RELATED_TO', 'AFFECTS', 'CONCERNS', 'TRIGGERS']
) YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;

CALL gds.graph.project(
  'finUndirected',
  ['Operation', 'Account', 'Counterparty', 'Category', 'Budget', 'Report', 'Risk'],
  {
    FROM_ACCOUNT: {orientation: 'UNDIRECTED'}, TO_ACCOUNT: {orientation: 'UNDIRECTED'},
    IN_CATEGORY: {orientation: 'UNDIRECTED'}, WITH_COUNTERPARTY: {orientation: 'UNDIRECTED'},
    SUBCATEGORY_OF: {orientation: 'UNDIRECTED'}, INCLUDES: {orientation: 'UNDIRECTED'},
    SUMMARIZES: {orientation: 'UNDIRECTED'}, AGGREGATES: {orientation: 'UNDIRECTED'},
    RELATED_TO: {orientation: 'UNDIRECTED'}, AFFECTS: {orientation: 'UNDIRECTED'},
    CONCERNS: {orientation: 'UNDIRECTED'}, TRIGGERS: {orientation: 'UNDIRECTED'}
  }
) YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
