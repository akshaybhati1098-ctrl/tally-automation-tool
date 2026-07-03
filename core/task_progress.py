from __future__ import annotations

import copy
import time
import uuid
from threading import RLock
from typing import Any, Dict, Optional


TERMINAL_STATUSES = {"completed", "failed"}


class TaskProgressStore:
    """Thread-safe in-memory progress store for user-scoped long-running tasks."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def create(self, user_id: str, task_type: str, title: str) -> str:
        task_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "user_id": str(user_id),
                "task_type": task_type,
                "title": title,
                "status": "queued",
                "message": "Queued",
                "created_at": now,
                "updated_at": now,
                "started_at": now,
                "completed_at": None,
                "progress": {
                    "ledger_count": 0,
                    "current_row": 0,
                    "total_rows": 0,
                    "percentage": 0,
                    "matched": 0,
                    "review": 0,
                    "not_matched": 0,
                },
                "result": None,
                "error": None,
            }
        return task_id

    def update(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        message: Optional[str] = None,
        progress: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if status is not None:
                task["status"] = status
            if message is not None:
                task["message"] = message
            if progress:
                task["progress"].update(progress)
            task["updated_at"] = time.time()

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["status"] = "completed"
            task["message"] = "Matching completed"
            task["result"] = result
            task["completed_at"] = time.time()
            task["updated_at"] = task["completed_at"]

    def fail(self, task_id: str, message: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["status"] = "failed"
            task["message"] = message
            task["error"] = message
            task["completed_at"] = time.time()
            task["updated_at"] = task["completed_at"]

    def snapshot(self, task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or str(task["user_id"]) != str(user_id):
                return None
            snapshot = copy.deepcopy(task)

        end_time = snapshot.get("completed_at") or time.time()
        snapshot["elapsed_seconds"] = max(
            0, int(end_time - snapshot.get("started_at", end_time))
        )
        snapshot["is_terminal"] = snapshot.get("status") in TERMINAL_STATUSES
        return snapshot

    def result(self, task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        snapshot = self.snapshot(task_id, user_id)
        if not snapshot:
            return None
        return snapshot.get("result")


task_progress_store = TaskProgressStore()
