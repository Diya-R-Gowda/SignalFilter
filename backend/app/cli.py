import argparse

from app.db import SessionLocal, init_db
from app.services.focus import get_current_focus, set_focus


def cmd_focus(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        state = set_focus(session, args.text)
        print(f"Focus set to: {state.focus_text!r}")
    finally:
        session.close()


def cmd_run(_args: argparse.Namespace) -> None:
    from app.connectors.slack_connector import start_slack_listener

    session = SessionLocal()
    try:
        focus_text = get_current_focus(session)
    finally:
        session.close()

    if not focus_text:
        print("No focus set yet. Run `python -m app.cli focus \"your focus text\"` first (in another terminal is fine while this runs).")
        return

    print(f"Current focus: {focus_text!r}")
    print("Listening on Slack (Socket Mode)... Ctrl+C to stop.")
    print("Tip: run `python -m app.cli focus \"new text\"` in another terminal any time to update your focus live.")
    start_slack_listener()


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(prog="signalfilter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    focus_parser = subparsers.add_parser("focus", help="Set your current focus text")
    focus_parser.add_argument("text", help="What you're currently focused on")
    focus_parser.set_defaults(func=cmd_focus)

    run_parser = subparsers.add_parser("run", help="Start the Slack listener + triage pipeline")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
