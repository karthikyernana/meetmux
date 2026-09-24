"""Job dispatcher and tracking service."""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from app.core.logging import get_logger

logger = get_logger(__name__)

# In-process thread pool for non-blocking task execution
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="planguard_worker")

# In-memory registry of job status
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def submit_job(func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Submit a synchronous task to the background executor and return job_id."""
    job_id = str(uuid.uuid4())
    now = datetime.utcnow()

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "QUEUED",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

    def _runner() -> None:
        with _jobs_lock:
            _jobs[job_id]["status"] = "RUNNING"
            _jobs[job_id]["started_at"] = datetime.utcnow()

        try:
            logger.info("job.started", job_id=job_id, task=func.__name__)
            res = func(*args, **kwargs)
            with _jobs_lock:
                _jobs[job_id]["status"] = "COMPLETED"
                _jobs[job_id]["completed_at"] = datetime.utcnow()
                _jobs[job_id]["result"] = res
            logger.info("job.completed", job_id=job_id)
        except Exception as exc:
            logger.error("job.failed", job_id=job_id, error=str(exc))
            with _jobs_lock:
                _jobs[job_id]["status"] = "FAILED"
                _jobs[job_id]["completed_at"] = datetime.utcnow()
                _jobs[job_id]["error"] = str(exc)

    _executor.submit(_runner)
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve job metadata and current status."""
    with _jobs_lock:
        return _jobs.get(job_id)
