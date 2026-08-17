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

    from app.connectors.calendar_connector import start_calendar_listener
    from app.digest import start_digest_scheduler
    from app.services.flow_state import start_flow_state_logger
    from app.services.repo_index import start_repo_index_refresher

    # Not per-connector-source — calendar informs every incoming message regardless of
    # which of Slack/Gmail is running, same "starts exactly once" requirement digest
    # mode established, so it's not gated behind --source the way Slack/Gmail are.
    threading.Thread(target=start_digest_scheduler, daemon=True).start()
    threading.Thread(target=start_calendar_listener, daemon=True).start()
    # Validation-phase only (see flow_state.py) — logs real (idle, process) samples during
    # normal daily use so flow-state calibration constants can be checked against real data
    # before any suppression logic is written. Does not affect notify decisions yet.
    threading.Thread(target=start_flow_state_logger, daemon=True).start()
    print("Flow-state data gathering started (validation phase only — not yet affecting notifications).")
    # GitHub-aware auto-reply (Tier A) — keeps the in-memory commit index fresh so incoming
    # Slack questions can be matched against recent commits without a live git call per message.
    threading.Thread(target=start_repo_index_refresher, daemon=True).start()

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


def cmd_audit(args: argparse.Namespace) -> None:
    import json
    from pathlib import Path

    from app.services.embedding import similarity
    from app.services.llm import score_item

    golden_set_path = Path(__file__).resolve().parent.parent / "tests" / "golden_set.json"
    with open(golden_set_path, encoding="utf-8") as f:
        golden_set = json.load(f)

    total = 0
    failures = 0

    for case in golden_set["llm_cases"]:
        total += 1
        actual_score, actual_reason = score_item(
            case["focus_text"], case["content"], case["sender"], case["source"]
        )
        if actual_score == case["expected_score"]:
            print(f"PASS  llm/{case['name']}")
        else:
            failures += 1
            print(
                f"FAIL  llm/{case['name']}: expected score {case['expected_score']}, "
                f"got {actual_score} (reason: {actual_reason!r})"
            )

    for case in golden_set["embedding_cases"]:
        total += 1
        actual_similarity = similarity(case["focus_text"], case["content"])
        # Tight epsilon rather than exact float equality — determinism was verified
        # live (23 LLM calls, 6 embedding calls, zero variance), this just guards
        # against harmless float round-tripping through JSON serialization.
        if abs(actual_similarity - case["expected_similarity"]) < 1e-4:
            print(f"PASS  embedding/{case['name']}")
        else:
            failures += 1
            print(
                f"FAIL  embedding/{case['name']}: expected similarity "
                f"{case['expected_similarity']}, got {actual_similarity}"
            )

    print(f"\n{total - failures}/{total} passed")
    if failures:
        sys.exit(1)


def main() -> None:
    # Message content (Slack/Gmail) can contain emoji or other non-ASCII characters. Windows'
    # default console/file encoding (cp1252) can't print those, crashing mid-poll and — for
    # Gmail — preventing the history cursor from ever advancing past the failing message.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from app.services.app_identity import ensure_app_identity
    ensure_app_identity()

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

    audit_parser = subparsers.add_parser(
        "audit", help="Run the golden-set regression check against the LLM judge and embedding model"
    )
    audit_parser.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
