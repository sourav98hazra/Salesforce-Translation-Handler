"""Tests for the wakelock module with mocked platform calls."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from stx.wakelock import WakeLock, prevent_sleep, _build_platform_lock, _NoopLock


def test_context_manager_acquire_release():
    """prevent_sleep context manager calls acquire and release."""
    with patch("stx.wakelock._build_platform_lock") as mock_build:
        mock_impl = MagicMock()
        mock_build.return_value = mock_impl

        with prevent_sleep("test reason") as lock:
            assert lock.held is True
            mock_impl.acquire.assert_called_once()

        mock_impl.release.assert_called_once()


def test_wakelock_acquire_failure_graceful():
    """If acquire fails, WakeLock degrades gracefully."""
    with patch("stx.wakelock._build_platform_lock") as mock_build:
        mock_impl = MagicMock()
        mock_impl.acquire.side_effect = RuntimeError("no tool")
        mock_build.return_value = mock_impl

        lock = WakeLock("test")
        result = lock.acquire()
        assert result is False
        assert lock.held is False


def test_platform_dispatch_darwin():
    with patch("stx.wakelock.platform.system", return_value="Darwin"):
        impl = _build_platform_lock("test")
        assert "MacCaffeinate" in type(impl).__name__


def test_platform_dispatch_windows():
    with patch("stx.wakelock.platform.system", return_value="Windows"):
        impl = _build_platform_lock("test")
        assert "WindowsExecutionState" in type(impl).__name__


def test_platform_dispatch_linux_with_systemd():
    with patch("stx.wakelock.platform.system", return_value="Linux"):
        with patch("stx.wakelock.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            impl = _build_platform_lock("test")
            assert "LinuxSystemdInhibit" in type(impl).__name__


def test_platform_dispatch_linux_without_systemd():
    with patch("stx.wakelock.platform.system", return_value="Linux"):
        with patch("stx.wakelock.subprocess.run", side_effect=FileNotFoundError):
            impl = _build_platform_lock("test")
            assert isinstance(impl, _NoopLock)


def test_platform_dispatch_unknown():
    with patch("stx.wakelock.platform.system", return_value="FreeBSD"):
        impl = _build_platform_lock("test")
        assert isinstance(impl, _NoopLock)


def test_noop_lock_does_nothing():
    lock = _NoopLock()
    lock.acquire()  # should not raise
    lock.release()  # should not raise
