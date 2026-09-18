from __future__ import annotations

from app.config import Settings
from app.providers.vector_store.local import LocalVectorStore
from app.providers.vector_store.pinecone_store import PineconeVectorStore


def create_vector_store(settings: Settings):
    if settings.vector_store == "local":
        return LocalVectorStore(settings.vector_store_dir, dimension=settings.pinecone_dimension)
    if settings.vector_store == "pinecone":
        key = settings.pinecone_api_key.get_secret_value() if settings.pinecone_api_key else ""
        if not key:
            raise ValueError(
                "VECTOR_STORE=pinecone requires PINECONE_API_KEY; refusing silent fallback to local"
            )
        return PineconeVectorStore(
            api_key=key,
            index_name=settings.pinecone_index_name,
            namespace=settings.vector_namespace,
            dimension=settings.pinecone_dimension,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        )
    raise ValueError(f"Unknown VECTOR_STORE={settings.vector_store}")
