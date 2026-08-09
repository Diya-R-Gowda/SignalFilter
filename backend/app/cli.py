import argparse
import sys

from app.db import SessionLocal, init_db
from app.services.focus import get_current_focus, set_focus


def cmd_focus(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        state = set_focus(session, args.text)
        print(f"Focus set to: {state.focus_text!r}")
    finally:
        session.close()


def cmd_run(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        focus_text = get_current_focus(session)
    finally:
        session.close()

    if not focus_text:
        print("No focus set yet. Run `python -m app.cli focus \"your focus text\"` first (in another terminal is fine while this runs).")
        return

    print(f"Current focus: {focus_text!r}")
    print("Tip: run `python -m app.cli focus \"new text\"` in another terminal any time to update your focus live.")

    sources = args.source
    listeners = []

    if sources in ("slack", "all"):
        from app.connectors.slack_connector import start_slack_listener
        listeners.append(("Slack (Socket Mode)", start_slack_listener))

    if sources in ("gmail", "all"):
        from app.connectors.gmail_connector import start_gmail_listener
        listeners.append(("Gmail (polling)", start_gmail_listener))

    import threading

    from app.digest import start_digest_scheduler

    # Not per-connector — reads across all sources regardless of --source, so it starts
    # exactly once here rather than inside either connector module.
    threading.Thread(target=start_digest_scheduler, daemon=True).start()

    if len(listeners) == 1:
        name, start_fn = listeners[0]
        print(f"Listening on {name}... Ctrl+C to stop.")
        start_fn()
        return

    print(f"Listening on {', '.join(name for name, _ in listeners)}... Ctrl+C to stop.")
    threads = [threading.Thread(target=start_fn, daemon=True) for _, start_fn in listeners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def main() -> None:
    # Message content (Slack/Gmail) can contain emoji or other non-ASCII characters. Windows'
    # default console/file encoding (cp1252) can't print those, crashing mid-poll and — for
    # Gmail — preventing the history cursor from ever advancing past the failing message.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    init_db()

    parser = argparse.ArgumentParser(prog="signalfilter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    focus_parser = subparsers.add_parser("focus", help="Set your current focus text")
    focus_parser.add_argument("text", help="What you're currently focused on")
    focus_parser.set_defaults(func=cmd_focus)

    run_parser = subparsers.add_parser("run", help="Start the connector(s) + triage pipeline")
    run_parser.add_argument(
        "--source",
        choices=["slack", "gmail", "all"],
        default="all",
        help="Which connector(s) to run (default: all)",
    )
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
