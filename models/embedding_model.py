# -*- coding: utf-8 -*-
"""
Created on Tue Mar  3 15:11:38 2026

@author: THYAGHARAJAN
"""

from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np


class EmbeddingModel:
    """
    Handles embedding generation for documents and queries.
    Fully offline model loading.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for multiple document chunks.
        Returns a NumPy array of shape (n_chunks, embedding_dim)
        """
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Generate embedding for a single query.
        Returns a NumPy array of shape (embedding_dim,)
        """
        embedding = self.model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embedding