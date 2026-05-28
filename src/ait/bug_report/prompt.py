from __future__ import annotations

import os
import sys
from typing import Callable, TextIO

from ait.bug_report import collector as collector_mod
from ait.bug_report.builder import build_issue
from ait.bug_report.config import BugReportPrefs, load_prefs, save_prefs
from ait.bug_report.flush import decide_prompt
from ait.bug_report.pending_queue import PendingReport, enqueue
from ait.bug_report.safety import _safe
from ait.bug_report.seen_store import record_seen, record_submitted
from ait.bug_report.submitter import submit


def _find_repo_root() -> "str | None":
    """Walk up from cwd looking for a .ait directory."""
    from pathlib import Path
    try:
        current = Path.cwd()
    except (FileNotFoundError, OSError):
        return None
    for candidate in [current, *current.parents]:
        if (candidate / ".ait").is_dir():
            return str(candidate)
    return None


@_safe
def _collect_tier2(prefs: BugReportPrefs) -> dict:
    """Collect Tier 2 context: install_nonce, daemon log tail, daemon state, phase."""
    if not prefs.include_tier2:
        return {}
    import socket
    from pathlib import Path

    install_nonce = ""
    daemon_log_tail = ""
    daemon_state = ""
    phase = ""

    repo_root = _find_repo_root()
    if repo_root:
        try:
            from ait.config import load_local_config
            cfg = load_local_config(repo_root)
            if cfg and cfg.install_nonce:
                install_nonce = cfg.install_nonce[:8]
        except Exception:
            pass

        try:
            log_path = Path(repo_root) / ".ait" / "daemon.log"
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                daemon_log_tail = "\n".join(lines[-20:])
        except Exception:
            pass

        try:
            sock_path = Path(repo_root) / ".ait" / "daemon.sock"
            if sock_path.exists():
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                try:
                    s.connect(str(sock_path))
                    daemon_state = "running"
                except (socket.timeout, ConnectionRefusedError, OSError):
                    daemon_state = "unreachable"
                finally:
                    s.close()
            else:
                daemon_state = "down"
        except Exception:
            daemon_state = ""

    # Phase: prefer AIT_PHASE env var, else first non-option argv token.
    phase = os.environ.get("AIT_PHASE", "")
    if not phase:
        for arg in sys.argv[1:]:
            if not arg.startswith("-"):
                phase = arg
                break

    return {
        "install_nonce": install_nonce,
        "daemon_log_tail": daemon_log_tail,
        "daemon_state": daemon_state,
        "phase": phase,
    }


@_safe
def _collect_tier3(prefs: BugReportPrefs) -> dict:
    """Collect Tier 3 context: whitelisted env vars."""
    if not prefs.include_tier3:
        return {}
    result: dict[str, str] = {}
    for key in ("PATH", "EDITOR"):
        val = os.environ.get(key)
        if val is not None:
            result[key] = val
    for key, val in os.environ.items():
        if key.startswith("AIT_"):
            result[key] = val
    return result


def _build_input(entries, prefs: BugReportPrefs):
    import platform
    from ait.bug_report.builder import BuildInput
    try:
        from ait.cli_installation import package_version
        ait_version = package_version()
    except Exception:
        ait_version = "unknown"

    tier2 = _collect_tier2(prefs) or {}
    tier3 = _collect_tier3(prefs) or {}

    return BuildInput(
        entries=entries,
        ait_version=ait_version,
        python_version=platform.python_version(),
        os_arch=f"{platform.system().lower()}/{platform.machine()}",
        argv=list(sys.argv),
        include_tier2=prefs.include_tier2,
        include_tier3=prefs.include_tier3,
        install_nonce=tier2.get("install_nonce", ""),
        daemon_log_tail=tier2.get("daemon_log_tail", ""),
        daemon_state=tier2.get("daemon_state", ""),
        phase=tier2.get("phase", ""),
        env_vars=tier3,
        extra_transcript=None,
        repo_id=None,
    )


def interactive_flush(
    *,
    input_provider: Callable[[str], str],
    is_tty: bool,
    stdout: TextIO,
    stderr: TextIO,
    now: str,
) -> None:
    decision = decide_prompt(now=now)
    if decision.action != "prompt":
        return

    prefs = load_prefs()
    issue = build_issue(_build_input(decision.to_prompt, prefs))

    if not is_tty:
        # Non-interactive: defer to pending queue.
        enqueue(PendingReport(
            fingerprint=issue.primary_fingerprint,
            title=issue.title, body=issue.body,
            category=decision.to_prompt[0].category,
            created_at=now,
        ))
        n = len(decision.to_prompt)
        print(
            f"ait: {n} internal error(s) saved to pending. "
            f"Run `ait bug-report --replay --all` to send.",
            file=stderr,
        )
        return

    # Mark seen regardless of user choice.
    for e in decision.to_prompt:
        record_seen(e.fingerprint, category=e.category, now=now)

    # First-time setup if mode is unset.
    if prefs.mode == "unset":
        print(_first_time_text(), file=stdout)
        choice = (input_provider("Choice [1]: ") or "1").strip()
        new_mode = {"1": "ask", "2": "always", "3": "never"}.get(choice, "ask")
        prefs.mode = new_mode
        prefs.first_setup_at = now
        save_prefs(prefs)
        if new_mode == "never":
            return

    if prefs.mode == "ask":
        print(_summary(decision.to_prompt), file=stdout)
        ans = (input_provider(
            "Send a bug report to help improve AIT? [y/n/s/a]: "
        ) or "n").strip().lower()
        if ans == "s":
            prefs.mode = "never"
            save_prefs(prefs)
            return
        if ans == "a":
            # "always ask for next time too" — keep mode=ask, still proceed to review.
            save_prefs(prefs)
        elif ans not in ("y", "yes"):
            # "n" or anything else: skip submission this time.
            return

    # Review screen.
    print("\n----- Review -----", file=stdout)
    print(f"Title: {issue.title}", file=stdout)
    print(issue.body, file=stdout)
    print("------------------", file=stdout)
    confirm = (input_provider("[s] send  [x] cancel: ") or "x").strip().lower()
    if confirm != "s":
        return

    result = submit(title=issue.title, body=issue.body)
    if result.status == "ok":
        record_submitted(
            issue.primary_fingerprint,
            issue_url=result.issue_url,
            method=result.method or "url",
            now=now,
        )
        if result.issue_url:
            print(f"sent: {result.issue_url}", file=stdout)
        else:
            print("sent (browser).", file=stdout)
    else:
        enqueue(PendingReport(
            fingerprint=issue.primary_fingerprint,
            title=issue.title, body=issue.body,
            category=decision.to_prompt[0].category,
            created_at=now,
        ))
        print("save to pending — replay with `ait bug-report --replay`.",
              file=stdout)


def _first_time_text() -> str:
    return (
        "ait noticed an internal error. AIT can send a bug report to help fix it.\n"
        "\n"
        "What gets sent: stack trace, AIT/Python version, OS, the command you ran.\n"
        "You'll always see the exact contents and approve before anything is sent.\n"
        "\n"
        "How should AIT handle bug reports?\n"
        "  [1] Ask me each time     (default)\n"
        "  [2] Always ask to send   (skip 'report?', still review contents)\n"
        "  [3] Never                (turn off bug reporting)\n"
    )


def _summary(entries) -> str:
    lines = [f"ait encountered {len(entries)} internal error(s) during this run.", ""]
    for e in entries:
        lines.append(f"  • {e.category}  (×{e.count})  [{e.fingerprint}]")
    lines.append("")
    lines.append("  [y] yes, review and send")
    lines.append("  [n] not now")
    lines.append("  [s] not now, and stop asking")
    lines.append("  [a] always ask for next time too")
    return "\n".join(lines)
