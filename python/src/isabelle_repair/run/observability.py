from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


@dataclass
class JsonEventLogger:
    run_id: str
    stream: TextIO
    level: int = logging.INFO

    def emit(
        self,
        event: str,
        *,
        state: str,
        task_id: str | None = None,
        level: str = "INFO",
        payload: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "event": event,
            "run_id": self.run_id,
            "task_id": task_id,
            "state": state,
            "payload": payload or {},
        }
        self.stream.write(json.dumps(record, ensure_ascii=True) + "\n")
        self.stream.flush()


@dataclass
class MultiEventLogger:
    loggers: list[JsonEventLogger]

    def emit(self, event: str, **kwargs: Any) -> None:
        for logger in self.loggers:
            logger.emit(event, **kwargs)


def default_stdout_logger(run_id: str) -> JsonEventLogger:
    return JsonEventLogger(run_id=run_id, stream=sys.stdout)


def file_logger(run_id: str, path: Path) -> JsonEventLogger:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8")
    return JsonEventLogger(run_id=run_id, stream=handle)
