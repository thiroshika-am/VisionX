"""
Tests for VisionX System Monitor.
Run: python -m pytest tests/test_system_monitor.py -v
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestSystemMonitor:

    @pytest.fixture
    def monitor(self):
        from core.system_monitor import SystemMonitor
        return SystemMonitor(fps_window_sec=2.0)

    def test_get_stats_returns_dict(self, monitor):
        stats = monitor.get_stats()
        assert isinstance(stats, dict)

    def test_cpu_in_range(self, monitor):
        stats = monitor.get_stats()
        assert "cpu_percent" in stats
        assert 0 <= stats["cpu_percent"] <= 100

    def test_ram_in_range(self, monitor):
        stats = monitor.get_stats()
        assert "ram_percent" in stats
        assert 0 <= stats["ram_percent"] <= 100
        assert stats["ram_total_mb"] > 0

    def test_fps_starts_at_zero(self, monitor):
        fps = monitor.get_fps()
        assert fps == 0.0

    def test_fps_updates_after_frames(self, monitor):
        for _ in range(10):
            monitor.record_frame()
            time.sleep(0.05)
        fps = monitor.get_fps()
        assert fps > 0.0

    def test_gpu_field_present(self, monitor):
        stats = monitor.get_stats()
        assert "gpu_available" in stats

    def test_uptime_increases(self, monitor):
        stats1 = monitor.get_stats()
        time.sleep(0.1)
        stats2 = monitor.get_stats()
        assert stats2["uptime_sec"] >= stats1["uptime_sec"]

    def test_singleton(self):
        from core.system_monitor import get_monitor
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2


class TestStructuredLogger:

    @pytest.fixture
    def log_dir(self, tmp_path):
        return str(tmp_path)

    @pytest.fixture
    def vx_logger(self, log_dir):
        from core.logger import VisionXLogger
        return VisionXLogger(logs_dir=log_dir)

    def test_log_event_creates_file(self, vx_logger, log_dir):
        vx_logger.log_event("test", "Hello from test")
        path = os.path.join(log_dir, "events.jsonl")
        assert os.path.exists(path)

    def test_log_detection(self, vx_logger, log_dir):
        result = {
            "count": 1, "alert_level": "SAFE",
            "detections": [{"class": "person", "confidence": 0.9}]
        }
        vx_logger.log_detection(result)
        path = os.path.join(log_dir, "detections.jsonl")
        assert os.path.exists(path)

    def test_log_performance(self, vx_logger, log_dir):
        vx_logger.log_performance(fps=24.5, cpu=32.0, ram=60.0, processing_ms=45)
        path = os.path.join(log_dir, "performance.jsonl")
        assert os.path.exists(path)
