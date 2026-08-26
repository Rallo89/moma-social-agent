#!/usr/bin/env python3
"""PreToolUse: chiede conferma prima di una pubblicazione reale su Instagram.

I workflow schedulati pubblicano da soli — e' il comportamento voluto. Questo
hook riguarda solo i comandi lanciati a mano dentro una sessione Claude Code,
dove un `momasocial weekly` senza `--dry-run` manderebbe un post online
immediatamente, magari mentre si stava solo provando un template.
"""

import json
import re
import sys

PUBLISHING = re.compile(r"\bmomasocial\b.*\b(weekly|format|results)\b")
SAFE = ("--dry-run", "--no-publish")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if event.get("tool_name") != "Bash":
        return 0
    command = event.get("tool_input", {}).get("command", "")
    if not PUBLISHING.search(command) or any(flag in command for flag in SAFE):
        return 0

    reason = (
        "Questo comando pubblica davvero su Instagram (nessun --dry-run "
        "ne' --no-publish). Conferma solo se il post e' stato rivisto; "
        "altrimenti rilancialo con --no-publish per generare l'anteprima."
    )
    if "--force" in command:
        reason += (
            " Attenzione: --force scavalca anche il controllo anti-doppione "
            "del ledger."
        )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
