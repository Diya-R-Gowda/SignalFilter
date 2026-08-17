import ctypes
import subprocess
import sys
from pathlib import Path

# Permanent AUMID for this app. Windows requires a Start Menu shortcut carrying this exact
# AUMID before ANY toast from a process claiming it is allowed to render interactive elements
# (buttons/inputs) — confirmed via the win11toast feasibility investigation (CONTRIBUTING.md),
# first with a throwaway test AUMID, now with this permanent one.
#
# Deliberately NOT "SignalFilter.App" — an earlier shortcut-creation script had a bug (a bad
# IShellLinkW->IPropertyStore COM cast) that silently failed to write the shortcut file at all
# while still calling win11toast under that AUMID. Windows appears to cache a negative/broken
# registration per-AUMID from that first failed attempt: even after the shortcut-creation bug
# was fixed and the file verifiably persisted correctly on disk, "SignalFilter.App" still never
# rendered buttons, while an identical setup under a fresh, never-before-used AUMID worked
# immediately. Rather than fight a Windows-side cache with unknown invalidation rules, this
# uses a clean AUMID that was never touched by the broken attempts.
APP_USER_MODEL_ID = "SignalFilter.Notifier"
APP_DISPLAY_NAME = "Signal Filter"

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SHORTCUT_PATH = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / f"{APP_DISPLAY_NAME}.lnk"
)
CREATE_SHORTCUT_SCRIPT = BACKEND_DIR / "scripts" / "create_app_shortcut.ps1"


def ensure_app_identity() -> None:
    """Call once at process startup, before any toast fires. Sets this process's explicit
    AUMID (cheap, always safe to redo) and creates the one-time Start Menu shortcut carrying
    that same AUMID if it doesn't exist yet — without it, win11toast falls back to the
    generic 'Python' app identity, which Windows silently refuses to render buttons under."""
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)

    if SHORTCUT_PATH.exists():
        return

    python_exe = sys.executable
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", str(CREATE_SHORTCUT_SCRIPT),
            "-ShortcutPath", str(SHORTCUT_PATH),
            "-TargetPath", python_exe,
            "-AppUserModelId", APP_USER_MODEL_ID,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[app_identity] failed to create Start Menu shortcut: {result.stderr.strip()}")
        print("[app_identity] actionable toast buttons will not render until this is fixed.")
    else:
        print(f"[app_identity] {result.stdout.strip()}")
