"""Capability module for semantic layer extraction, resolution, persistence, and aggregation."""

from capability.models import (
    CapabilityKind,
    ExtractedCapability,
    CapabilityExtractionResult,
)
from capability.normalization import (
    normalize,
    to_capability_id,
    is_generic,
)
from capability.extraction import (
    CapabilityExtractor,
    LLMBackend,
    FakeLLM,
)
from capability.resolution import (
    CapabilityResolver,
    CapabilityRecord,
    Embedder,
    NoEmbedder,
)
from capability.repository import CapabilityRepository
from capability.aggregation import (
    CapabilityAggregator,
    AuthorCapabilityAggregate,
)

__all__ = [
    "CapabilityKind",
    "ExtractedCapability",
    "CapabilityExtractionResult",
    "normalize",
    "to_capability_id",
    "is_generic",
    "CapabilityExtractor",
    "LLMBackend",
    "FakeLLM",
    "CapabilityResolver",
    "CapabilityRecord",
    "Embedder",
    "NoEmbedder",
    "CapabilityRepository",
    "CapabilityAggregator",
    "AuthorCapabilityAggregate",
]
