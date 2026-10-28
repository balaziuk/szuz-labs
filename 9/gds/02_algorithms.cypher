CALL gds.pageRank.write('finDirected', {
  writeProperty: 'pagerank', maxIterations: 20, dampingFactor: 0.85
}) YIELD nodePropertiesWritten, ranIterations, didConverge
RETURN nodePropertiesWritten, ranIterations, didConverge;

CALL gds.louvain.write('finUndirected', {
  writeProperty: 'community', concurrency: 1
}) YIELD communityCount, modularity, nodePropertiesWritten
RETURN communityCount, modularity, nodePropertiesWritten;
