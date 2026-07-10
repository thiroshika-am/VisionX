"""
System Monitor — Real-time CPU, RAM, GPU, FPS tracking.
Uses psutil for system metrics and tracks inference FPS from frame timestamps.
"""

import time
import threading
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[SystemMonitor] psutil not installed. Run: pip install psutil")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class SystemMonitor:
    def __init__(self, fps_window_sec: float = 5.0):
        self._fps_window   = fps_window_sec
        self._frame_times  = []
        self._fps_lock     = threading.Lock()
        self._start_time   = time.time()
        # Pre-warm psutil CPU (first call returns 0)
        if PSUTIL_AVAILABLE:
            psutil.cpu_percent(interval=None)

    # ── Frame tracking ────────────────────────────────────────────────────────

    def record_frame(self):
        """Call once per processed frame to update FPS counter."""
        now = time.time()
        with self._fps_lock:
            self._frame_times.append(now)
            cutoff = now - self._fps_window
            self._frame_times = [t for t in self._frame_times if t >= cutoff]

    def get_fps(self) -> float:
        with self._fps_lock:
            if len(self._frame_times) < 2:
                return 0.0
            span = self._frame_times[-1] - self._frame_times[0]
            return round(len(self._frame_times) / span, 1) if span > 0 else 0.0

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        stats: dict = {
            "fps":         self.get_fps(),
            "uptime_sec":  round(time.time() - self._start_time),
            "gpu_available": False,
        }

        if PSUTIL_AVAILABLE:
            mem = psutil.virtual_memory()
            stats.update({
                "cpu_percent":   round(psutil.cpu_percent(interval=None), 1),
                "cpu_count":     psutil.cpu_count(),
                "ram_percent":   round(mem.percent, 1),
                "ram_used_mb":   round(mem.used / 1024 / 1024),
                "ram_total_mb":  round(mem.total / 1024 / 1024),
            })
        else:
            stats.update({"cpu_percent": 0, "ram_percent": 0,
                          "ram_used_mb": 0, "ram_total_mb": 0})

        # GPU info (CUDA)
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                props  = torch.cuda.get_device_properties(0)
                alloc  = torch.cuda.memory_allocated(0)
                total  = props.total_memory
                stats.update({
                    "gpu_available":     True,
                    "gpu_name":          props.name,
                    "gpu_memory_used_mb": round(alloc / 1024 / 1024),
                    "gpu_memory_total_mb": round(total / 1024 / 1024),
                    "gpu_memory_percent": round(alloc / total * 100, 1) if total else 0,
                })
            except Exception:
                pass

        return stats


# Singleton
_monitor: Optional[SystemMonitor] = None


def get_monitor() -> SystemMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SystemMonitor()
    return _monitor
