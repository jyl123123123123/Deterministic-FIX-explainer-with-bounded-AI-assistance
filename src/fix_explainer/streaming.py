"""Cancellable, rate-limited replay of synthetic FIX messages."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .synthetic import SyntheticMessage, generate_synthetic_messages

MessageHandler = Callable[[SyntheticMessage], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class StreamConfig:
    count: int = 1500
    rate: int = 25
    seed: int = 20261010

    def __post_init__(self) -> None:
        if not 1000 <= self.count <= 2000:
            raise ValueError("count must be between 1000 and 2000")
        if not 10 <= self.rate <= 100:
            raise ValueError("rate must be between 10 and 100 messages per second")


@dataclass
class StreamRun:
    run_id: str
    config: StreamConfig
    status: str = "PENDING"
    processed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _stop_requested: bool = field(default=False, repr=False)
    _rate: int | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "processed": self.processed,
            "total_messages": self.config.count,
            "rate": self._rate or self.config.rate,
            "seed": self.config.seed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
        }


class StreamSimulator:
    """Replay messages in sequence and deliver each one to a consumer."""

    def __init__(self, message_handler: MessageHandler) -> None:
        self._message_handler = message_handler
        self._runs: dict[str, StreamRun] = {}

    def start(self, config: StreamConfig | None = None) -> StreamRun:
        """Start one replay task; reject a second concurrent run."""
        config = config or StreamConfig()
        if any(run.status in ("RUNNING", "PAUSED") for run in self._runs.values()):
            raise RuntimeError("a stream run is already active")
        run = StreamRun(run_id=f"run-{uuid4().hex[:12]}", config=config)
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc)
        self._runs[run.run_id] = run
        run._task = asyncio.create_task(self._run(run))
        return run

    async def stop(self, run_id: str) -> StreamRun:
        run = self._get_run(run_id)
        if run.status in ("RUNNING", "PAUSED"):
            run._stop_requested = True
            if run._task is not None:
                await run._task
        return run

    def control(self, run_id: str, action: str, rate: int | None = None) -> StreamRun:
        run = self._get_run(run_id)
        if run.status not in ("RUNNING", "PAUSED"):
            raise ValueError("Run is no longer active")
        if rate is not None:
            if not 10 <= rate <= 100:
                raise ValueError("Rate must be between 10 and 100")
            run._rate = rate
        run.status = "PAUSED" if action == "pause" else "RUNNING"
        return run

    async def wait(self, run_id: str) -> StreamRun:
        run = self._get_run(run_id)
        if run._task is not None:
            await run._task
        return run

    def status(self, run_id: str) -> dict[str, object]:
        return self._get_run(run_id).snapshot()

    def _get_run(self, run_id: str) -> StreamRun:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise KeyError(f"unknown stream run: {run_id}") from error

    async def _run(self, run: StreamRun) -> None:
        try:
            messages = generate_synthetic_messages(
                run.config.count,
                seed=run.config.seed,
                start_time=run.started_at,
            )
            for message in messages:
                while run.status == "PAUSED" and not run._stop_requested:
                    await asyncio.sleep(0.05)
                if run._stop_requested:
                    run.status = "STOPPED"
                    break
                result = self._message_handler(message)
                if inspect.isawaitable(result):
                    await result
                run.processed += 1
                await asyncio.sleep(1 / (run._rate or run.config.rate))
            else:
                run.status = "COMPLETED"
        except asyncio.CancelledError:
            run.status = "STOPPED"
            raise
        except Exception as error:
            run.status = "FAILED"
            run.error = str(error)
            raise
        finally:
            run.finished_at = datetime.now(timezone.utc)
