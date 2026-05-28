"""Cross-platform wake lock to keep the system awake during long runs.

The wake lock is best-effort: it asks the operating system not to enter
suspend / display-sleep while it's held.  All platforms allow the user
to override (e.g. closing a laptop lid still suspends on most systems
unless connected to AC power).  But for unattended translations that
finish in 5-15 minutes on AC power, this is the difference between a
clean run and an interrupted one.

Important caveats
-----------------
* **No app can survive an actual sleep.**  Once the OS suspends, every
  user-space process is paused -- there is no exception.  This module
  *prevents* sleep while the lock is held; it does not "run during"
  sleep.
* **Lid-close is special.**  On macOS in particular, closing the lid
  forces sleep regardless of any wake lock.  Keep the lid open.
* **Linux without systemd** has no widely supported inhibit mechanism;
  we degrade gracefully to a no-op there.

Usage
-----
::

    with prevent_sleep("Translation in progress"):
        translate_document(...)

The class form is also exposed for cases where the lock lifetime
doesn't match a single ``with`` block (e.g. a GUI thread).
"""

from __future__ import annotations

import logging
import platform
import subprocess
from contextlib import contextmanager
from typing import Iterator, Optional

LOGGER = logging.getLogger(__name__)


class WakeLock:
    """Best-effort cross-platform wake lock."""

    def __init__(self, reason: str = "Salesforce Translation Handler") -> None:
        self.reason = reason
        self._impl: Optional["_PlatformLock"] = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> bool:
        """Request that the OS stay awake.  Returns ``True`` on success."""
        if self._held:
            return True
        try:
            self._impl = _build_platform_lock(self.reason)
            self._impl.acquire()
        except Exception as exc:  # noqa: BLE001 -- best-effort
            LOGGER.debug("Wake lock acquire failed (%s); continuing without it.", exc)
            self._impl = None
            return False
        self._held = True
        return True

    def release(self) -> None:
        if not self._held or self._impl is None:
            return
        try:
            self._impl.release()
        except Exception:  # noqa: BLE001
            LOGGER.debug("Wake lock release raised", exc_info=True)
        finally:
            self._impl = None
            self._held = False


@contextmanager
def prevent_sleep(reason: str = "Translation in progress") -> Iterator[WakeLock]:
    """Context manager that holds a :class:`WakeLock` for the block."""
    lock = WakeLock(reason)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Platform-specific implementations
# ---------------------------------------------------------------------------

class _PlatformLock:
    """Base class -- subclasses override ``acquire`` / ``release``."""

    def acquire(self) -> None:  # pragma: no cover - overridden
        ...

    def release(self) -> None:  # pragma: no cover - overridden
        ...


class _MacCaffeinate(_PlatformLock):
    """Spawn ``caffeinate -dimsu`` as a child to block sleep / display sleep."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self._proc: Optional[subprocess.Popen] = None

    def acquire(self) -> None:
        # -d display | -i idle | -m disk | -s system (AC) | -u user-active
        self._proc = subprocess.Popen(
            ["caffeinate", "-d", "-i", "-m", "-s", "-u"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def release(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self._proc.kill()
        self._proc = None


class _WindowsExecutionState(_PlatformLock):
    """``SetThreadExecutionState`` to keep the system + display awake."""

    # Win32 constants -- documented at:
    # https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ES_AWAYMODE_REQUIRED = 0x00000040

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def acquire(self) -> None:
        import ctypes

        flags = (
            self.ES_CONTINUOUS
            | self.ES_SYSTEM_REQUIRED
            | self.ES_DISPLAY_REQUIRED
            | self.ES_AWAYMODE_REQUIRED
        )
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        if result == 0:
            raise OSError("SetThreadExecutionState returned 0 (failed)")

    def release(self) -> None:
        import ctypes

        # Resetting to ES_CONTINUOUS alone tells Windows we're done.
        ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)


class _LinuxSystemdInhibit(_PlatformLock):
    """Hold a ``systemd-inhibit`` lock while a child sleep process runs."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self._proc: Optional[subprocess.Popen] = None

    def acquire(self) -> None:
        # systemd-inhibit takes a child command and holds the lock for that
        # child's lifetime.  We use ``sleep infinity`` and reap it on release.
        self._proc = subprocess.Popen(
            [
                "systemd-inhibit",
                "--what=sleep:idle",
                "--who=stx",
                f"--why={self.reason}",
                "sleep",
                "infinity",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def release(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self._proc.kill()
        self._proc = None


class _NoopLock(_PlatformLock):
    """Fallback used when no wake-lock mechanism is available."""

    def acquire(self) -> None:
        LOGGER.debug("No wake-lock mechanism available on this platform.")

    def release(self) -> None:
        return None


def _build_platform_lock(reason: str) -> _PlatformLock:
    system = platform.system()
    if system == "Darwin":
        return _MacCaffeinate(reason)
    if system == "Windows":
        return _WindowsExecutionState(reason)
    if system == "Linux":
        # Probe for systemd-inhibit availability before committing.
        try:
            subprocess.run(
                ["systemd-inhibit", "--help"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return _LinuxSystemdInhibit(reason)
        except FileNotFoundError:
            return _NoopLock()
    return _NoopLock()
