import numpy as np
import pytest
import faiss

from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.storage.faiss_store import FAISSVectorStore


class StubEmbedder:
    def __init__(self, dim: int = 2) -> None:
        self.dim = dim
        self.calls = 0

    def embed(self, texts, batch_size: int = 1) -> np.ndarray:
        return np.zeros((len(texts), self.dim), dtype=np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        self.calls += 1
        return np.full(self.dim, float(self.calls), dtype=np.float32)


def test_inner_product_matches_cosine_after_normalization():
    vec_a = np.random.rand(384).astype(np.float32)
    vec_b = np.random.rand(384).astype(np.float32)
    norm_a = vec_a / np.linalg.norm(vec_a)
    norm_b = vec_b / np.linalg.norm(vec_b)
    cosine = float(np.dot(norm_a, norm_b))

    index = faiss.IndexFlatIP(norm_a.size)
    index.add(norm_a.reshape(1, -1))
    score = index.search(norm_b.reshape(1, -1), 1)[0][0][0]

    assert pytest.approx(cosine, abs=1e-6) == score


def test_manifest_invalidates_on_config_change(tmp_path):
    store = FAISSVectorStore(root=tmp_path)
    embeddings = np.ones((1, 2), dtype=np.float32)
    keys = [("doc", 0)]
    payload = {
        "embedding_model": "foo",
        "embedding_dim": 2,
        "similarity": "inner_product",
        "chunker": {"target_size": 100, "max_size": 200, "overlap": 1},
    }
    store.build(embeddings, keys, payload)
    assert store.manifest_matches(payload)

    changed_chunker = dict(payload)
    changed_chunker["chunker"] = {
        "target_size": 101,
        "max_size": 200,
        "overlap": 1,
    }
    assert not store.manifest_matches(changed_chunker)

    changed_model = dict(payload)
    changed_model["embedding_model"] = "bar"
    assert not store.manifest_matches(changed_model)


def test_dense_retriever_caches_queries():
    retriever = DenseRetriever(model_name="stub", embedder=StubEmbedder(dim=4))
    vec1 = retriever.encode_query("DYNA metrics")
    vec2 = retriever.encode_query("DYNA metrics")
    assert retriever.embedder.calls == 1
    assert np.allclose(vec1, vec2)
