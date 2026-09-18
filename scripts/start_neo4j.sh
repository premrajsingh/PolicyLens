#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose up -d
echo "Waiting for Neo4j..."
for i in $(seq 1 30); do
  if docker compose exec -T neo4j wget -qO- http://localhost:7474 >/dev/null 2>&1; then
    echo "Neo4j is up: http://localhost:7474  bolt://localhost:7687"
    echo "User: neo4j  Password: policylens_dev_password"
    exit 0
  fi
  sleep 2
done
echo "Neo4j did not become ready in time; check: docker compose logs neo4j"
exit 1
