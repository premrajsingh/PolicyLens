from __future__ import annotations

from app.config import Settings
from app.providers.graph_store.local import LocalGraphStore
from app.providers.graph_store.neo4j_store import Neo4jPolicyGraph

_neo4j_singleton: Neo4jPolicyGraph | None = None


def create_graph_store(settings: Settings):
    global _neo4j_singleton
    if settings.graph_store == "local":
        return LocalGraphStore(settings.graph_store_dir)
    if settings.graph_store == "neo4j":
        if _neo4j_singleton is not None:
            return _neo4j_singleton
        password = settings.neo4j_password.get_secret_value() if settings.neo4j_password else ""
        if not password:
            raise ValueError(
                "GRAPH_STORE=neo4j requires NEO4J_PASSWORD; refusing silent fallback to local"
            )
        _neo4j_singleton = Neo4jPolicyGraph(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=password,
            database=settings.neo4j_database,
        )
        return _neo4j_singleton
    raise ValueError(f"Unknown GRAPH_STORE={settings.graph_store}")


async def close_graph_store() -> None:
    global _neo4j_singleton
    store = _neo4j_singleton
    _neo4j_singleton = None
    if store is not None:
        await store.close()
