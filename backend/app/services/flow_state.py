import ctypes
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Validation-phase only: raw (idle_seconds, process_name) samples land here so Diya can
# hand-check whether derived "flow" periods actually line up with genuine focused stretches
# before any suppression logic gets wired into pipeline.py, per the plan's mandatory
# pre-ship validation gate (same one attention budget and weak-signal escalation used).
# Gitignored — even though this is just process names (never window titles), it's still
# personal activity data and shouldn't land in git history.
SAMPLE_LOG_PATH = BACKEND_DIR / "flow_state_samples.log"
SAMPLE_INTERVAL_SECONDS = 60


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> float:
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()
    millis_idle = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis_idle / 1000.0


def get_foreground_process_name() -> str | None:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
    )
    if not handle:
        return None

    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        # QueryFullProcessImageNameW, not the deprecated psapi GetModuleBaseName — works
        # across 32/64-bit process combinations without extra WOW64 handling.
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        ):
            return None
        full_path = buf.value
        return full_path.rsplit("\\", 1)[-1] if full_path else None
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def sample_once() -> tuple[float, str | None]:
    return get_idle_seconds(), get_foreground_process_name()


def start_flow_state_logger() -> None:
    """Validation-phase data gathering only. Appends (timestamp, idle_seconds, process_name)
    samples to SAMPLE_LOG_PATH every SAMPLE_INTERVAL_SECONDS. Does NOT write to SyncState and
    does NOT affect pipeline.py's threshold logic in any way — this exists purely to build up
    real days of (idle, process) samples to hand-check flow-state calibration constants
    against, per the plan's pre-ship validation requirement."""
    while True:
        try:
            idle_seconds, process_name = sample_once()
            timestamp = datetime.now(timezone.utc).isoformat()
            with open(SAMPLE_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{timestamp},{idle_seconds:.0f},{process_name or ''}\n")
        except Exception as exc:
            # Best-effort logging only — a transient ctypes/file error here must never take
            # down the process running the actual triage pipeline alongside it.
            print(f"[flow_state] sample failed: {exc}")
        time.sleep(SAMPLE_INTERVAL_SECONDS)
