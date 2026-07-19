"""The source contract. Every scraper implements this — nothing else changes.

New source = new Connector subclass + register one scheduler job.
No schema change, no touching ingest/scoring/dedup.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from datetime import datetime

from pydantic import BaseModel, Field


class SignalEnvelope(BaseModel):
    """Normalized output every connector emits — maps 1:1 onto the signal table."""

    source: str  # github|arxiv|devpost|producthunt|hn|synthetic|inbound
    signal_type: str  # commit|repo_release|paper|hackathon_win|launch|post|deck
    external_id: str  # source-native id; (source, external_id) unique → idempotent
    entity_hint: str | None = None  # raw handle/name for resolution ("github:torvalds")
    url: str | None = None
    title: str | None = None
    summary: str | None = None  # short normalized text → feed
    occurred_at: datetime | None = None
    source_reliability: float = 0.5  # per-source prior 0..1
    raw: dict = Field(default_factory=dict)  # full original payload, nothing discarded


class Connector(ABC):
    source: str

    @abstractmethod
    def fetch(self) -> Iterable[dict]:
        """Poll the source; yield raw records."""

    @abstractmethod
    def normalize(self, raw: dict) -> SignalEnvelope:
        """Map one raw record → SignalEnvelope."""

    def poll(self) -> Iterator[SignalEnvelope]:
        for raw in self.fetch():
            yield self.normalize(raw)
