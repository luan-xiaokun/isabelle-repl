from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from isabelle_repair.model import RunRecord, RunRecordKind


def serialize_run_record(record: RunRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "record_id": record.record_id,
        "theory_run_id": record.theory_run_id,
        "timestamp": record.timestamp,
        "run_local_sequence_number": record.run_local_sequence_number,
        "task_id": record.task_id,
        "record_kind": record.record_kind.value,
        "payload": record.payload,
    }


@dataclass
class RunRecordFactory:
    theory_run_id: str
    schema_version: str = "v1.5"
    _seq: int = 0

    def create(
        self,
        record_kind: RunRecordKind,
        task_id: str | None,
        payload: dict[str, object],
    ) -> RunRecord:
        self._seq += 1
        return RunRecord(
            record_id=f"rec-{uuid4().hex}",
            record_kind=record_kind,
            schema_version=self.schema_version,
            theory_run_id=self.theory_run_id,
            timestamp=RunRecord.now_iso(),
            run_local_sequence_number=self._seq,
            task_id=task_id,
            payload=payload,
        )


@dataclass
class InMemoryRecordStore:
    """Append-only in-memory store for tests and summaries."""

    _records: list[RunRecord] = field(default_factory=list)

    def append(self, record: RunRecord) -> None:
        self._records.append(record)

    def list_records(self) -> list[RunRecord]:
        return list(self._records)


@dataclass
class JsonlRecordSink:
    """Append each run record as one JSON line for replay/audit."""

    path: Path

    def append(self, record: RunRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(serialize_run_record(record), ensure_ascii=True))
            handle.write("\n")


@dataclass
class CompositeRecordStore:
    stores: list[object] = field(default_factory=list)

    def append(self, record: RunRecord) -> None:
        for store in self.stores:
            store.append(record)
