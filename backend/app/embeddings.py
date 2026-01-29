# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Purpose:
# Defines embedding provider interfaces and a stub implementation.
#
# Notes:
# Replace the stub with a real provider before production ingestion.

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from openai import OpenAI

from app.config import get_settings


@dataclass(frozen=True)
class EmbeddingProvider:
    name: str
    dimensions: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class StubEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise RuntimeError(
            "Embeddings provider is stubbed. Configure a real provider."
        )


def get_embedding_provider(name: str, dimensions: int) -> EmbeddingProvider:
    if name == "stub":
        return StubEmbeddingProvider(name=name, dimensions=dimensions)
    if name == "openai":
        return OpenAIEmbeddingProvider(name=name, dimensions=dimensions)
    raise ValueError(f"Unsupported embeddings provider: {name}")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: List[str]) -> List[List[float]]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")

        cleaned = [str(text).strip() for text in texts if str(text).strip()]
        if not cleaned:
            raise RuntimeError("No valid text provided for embeddings.")

        client = OpenAI(api_key=settings.openai_api_key)
        model = settings.embeddings_model or "text-embedding-3-small"
        embeddings: List[List[float]] = []
        for batch_start in range(0, len(cleaned), 64):
            batch = cleaned[batch_start : batch_start + 64]
            response = client.embeddings.create(model=model, input=batch)
            embeddings.extend([item.embedding for item in response.data])
        return embeddings

