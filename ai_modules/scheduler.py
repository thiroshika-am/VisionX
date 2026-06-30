"""
AI Module Scheduler for VisionX
Priority-based throttling scheduler that prevents multiple heavy AI models
from competing for compute simultaneously.

Tiers:
  - ALWAYS_ON:  obstacle detection (runs every frame)
  - PERIODIC:   face recognition, gesture recognition (timed intervals)
  - ON_DEMAND:  scene captioning, OCR, currency, object ID (voice/button triggered)
"""

import threading
import time
import logging
from enum import IntEnum
from collections import deque
from typing import Callable, Any, Optional, Dict

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Task priority levels. Lower number = higher priority."""
    CRITICAL = 0   # Safety-critical (obstacle alerts, SOS)
    HIGH = 1       # User-requested on-demand tasks (scene describe, OCR)
    MEDIUM = 2     # Periodic background tasks (face recognition)
    LOW = 3        # Low-priority periodic tasks (gesture recognition)


class SchedulerTask:
    """Represents a submitted task."""
    
    def __init__(self, name: str, priority: Priority, callable_fn: Callable,
                 args: tuple = (), kwargs: dict = None):
        self.name = name
        self.priority = priority
        self.callable_fn = callable_fn
        self.args = args
        self.kwargs = kwargs or {}
        self.submitted_at = time.time()
        self.result = None
        self.error = None
        self.completed = threading.Event()
    
    def wait(self, timeout: float = None) -> Any:
        """Block until the task completes and return the result."""
        self.completed.wait(timeout=timeout)
        if self.error:
            raise self.error
        return self.result


class ModuleScheduler:
    """
    Thread-safe priority scheduler for AI modules.
    
    Ensures only one heavy AI task runs at a time while allowing
    always-on tasks to bypass the queue.
    """
    
    def __init__(self):
        self._queue_lock = threading.Lock()
        self._task_queues: Dict[Priority, deque] = {
            p: deque() for p in Priority
        }
        self._running = False
        self._worker_thread = None
        self._current_task: Optional[str] = None
        self._current_task_lock = threading.Lock()
        
        # Stats
        self._stats = {
            "tasks_submitted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_dropped": 0,
        }
        self._stats_lock = threading.Lock()
        
        # Module throttle tracking: module_name -> last_run_timestamp
        self._last_run: Dict[str, float] = {}
        self._throttle_lock = threading.Lock()
    
    def start(self):
        """Start the scheduler worker thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("[Scheduler] Started")
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("[Scheduler] Stopped")
    
    def submit(self, name: str, priority: Priority, callable_fn: Callable,
               args: tuple = (), kwargs: dict = None,
               throttle_sec: float = 0) -> Optional[SchedulerTask]:
        """
        Submit a task to the scheduler.
        
        Args:
            name: Human-readable task name (e.g. "face_recognition")
            priority: Task priority level
            callable_fn: The function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            throttle_sec: Minimum seconds between runs of this task name
            
        Returns:
            SchedulerTask if submitted, None if throttled/dropped
        """
        # Check throttle
        if throttle_sec > 0:
            with self._throttle_lock:
                last = self._last_run.get(name, 0)
                if time.time() - last < throttle_sec:
                    return None
        
        task = SchedulerTask(name, priority, callable_fn, args, kwargs)
        
        with self._queue_lock:
            queue = self._task_queues[priority]
            # For periodic tasks, drop stale entries (keep queue bounded)
            if priority in (Priority.MEDIUM, Priority.LOW) and len(queue) >= 2:
                dropped = queue.popleft()
                dropped.error = RuntimeError("Dropped: queue full")
                dropped.completed.set()
                with self._stats_lock:
                    self._stats["tasks_dropped"] += 1
            
            queue.append(task)
            with self._stats_lock:
                self._stats["tasks_submitted"] += 1
        
        return task
    
    def submit_and_wait(self, name: str, priority: Priority, callable_fn: Callable,
                        args: tuple = (), kwargs: dict = None,
                        timeout: float = 30) -> Any:
        """Submit a task and block until it completes."""
        task = self.submit(name, priority, callable_fn, args, kwargs)
        if task is None:
            return None
        return task.wait(timeout=timeout)
    
    def get_current_task(self) -> Optional[str]:
        """Return the name of the currently executing task."""
        with self._current_task_lock:
            return self._current_task
    
    def get_stats(self) -> dict:
        """Return scheduler statistics."""
        with self._stats_lock:
            stats = dict(self._stats)
        with self._current_task_lock:
            stats["current_task"] = self._current_task
        return stats
    
    def is_throttled(self, name: str, interval_sec: float) -> bool:
        """Check if a named task is still within its throttle window."""
        with self._throttle_lock:
            last = self._last_run.get(name, 0)
            return (time.time() - last) < interval_sec
    
    def _worker_loop(self):
        """Main worker loop — processes tasks in priority order."""
        while self._running:
            task = self._get_next_task()
            if task is None:
                time.sleep(0.02)  # 20ms idle sleep
                continue
            
            with self._current_task_lock:
                self._current_task = task.name
            
            try:
                task.result = task.callable_fn(*task.args, **task.kwargs)
                with self._stats_lock:
                    self._stats["tasks_completed"] += 1
                with self._throttle_lock:
                    self._last_run[task.name] = time.time()
            except Exception as e:
                task.error = e
                logger.error(f"[Scheduler] Task '{task.name}' failed: {e}")
                with self._stats_lock:
                    self._stats["tasks_failed"] += 1
            finally:
                task.completed.set()
                with self._current_task_lock:
                    self._current_task = None
    
    def _get_next_task(self) -> Optional[SchedulerTask]:
        """Get the highest-priority pending task."""
        with self._queue_lock:
            for priority in Priority:
                queue = self._task_queues[priority]
                if queue:
                    return queue.popleft()
        return None


# Singleton instance
_scheduler_instance = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> ModuleScheduler:
    """Get or create the singleton scheduler instance."""
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = ModuleScheduler()
            _scheduler_instance.start()
        return _scheduler_instance
