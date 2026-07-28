"""Best-effort local state for transform diagnostics."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel

from voiceitt_bridge.transforms import TransformResponse, TransformStatus


DEFAULT_RECENT_TRANSFORM_LIMIT = 20


class TransformRecord(BaseModel):
    """Metadata-only record for one transform attempt.

    Raw and cleaned transcript text are intentionally excluded from this
    diagnostic shape. Any future persisted history must define explicit
    privacy and retention settings before text is stored.
    """

    id: str
    created_at: str
    status: TransformStatus
    failure_reason: str | None = None
    prompt_id: str
    prompt_version: str
    vocabulary_profile_ids: list[str]
    provider_id: str
    model: str
    source: str
    duration_ms: int
    raw_text_length: int
    cleaned_text_length: int


class CorrectionLedgerEntry(BaseModel):
    """Future correction metadata linked to a transform and optional target."""

    id: str
    created_at: str
    transform_record_id: str | None = None
    target_context_id: str | None = None
    correction_type: str
    notes: str | None = None


class TargetContext(BaseModel):
    """Future destination context for preview/debug grouping."""

    id: str
    name: str
    kind: str
    bundle_id: str | None = None
    command_name: str | None = None
    notes: str | None = None


class TransformStore(Protocol):
    """Best-effort transform diagnostic store interface."""

    def record(self, response: TransformResponse) -> TransformRecord | None:
        """Record transform metadata, or return None when disabled."""

    def recent(self) -> list[TransformRecord]:
        """Return newest transform records first."""


class InMemoryTransformStore:
    """Bounded in-process transform metadata store.

    This is intentionally not durable. It provides observability while
    keeping storage locked, missing, corrupt, slow, or disabled states
    out of the transform/send success path.
    """

    def __init__(self, *, max_records: int = DEFAULT_RECENT_TRANSFORM_LIMIT) -> None:
        self.max_records = max(0, max_records)
        self._records: deque[TransformRecord] = deque(maxlen=self.max_records or None)
        self._lock = Lock()

    def record(self, response: TransformResponse) -> TransformRecord | None:
        if self.max_records == 0:
            return None

        record = TransformRecord(
            id=str(uuid4()),
            created_at=_utc_now_iso(),
            status=response.status,
            failure_reason=response.failure_reason,
            prompt_id=response.prompt_id,
            prompt_version=response.prompt_version,
            vocabulary_profile_ids=response.vocabulary_profile_ids,
            provider_id=response.provider_id,
            model=response.model,
            source=response.source,
            duration_ms=response.duration_ms,
            raw_text_length=len(response.raw_text),
            cleaned_text_length=len(response.cleaned_text),
        )
        with self._lock:
            self._records.appendleft(record)
        return record

    def recent(self) -> list[TransformRecord]:
        with self._lock:
            return list(self._records)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
