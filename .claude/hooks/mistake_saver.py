#!/usr/bin/env python3
"""UserPromptSubmit: if the prompt looks like a correction, remind Claude to log it."""
import json
import re
import sys

PATTERNS = [
    r"\bthat'?s (wrong|not (it|right|what i))",
    r"\byou (broke|missed|forgot|ignored|messed)",
    r"^\s*(no|nope|wrong)[,.! ]",
    r"\bthat'?s (wrong|incorrect)\b",
    r"\bnot what i (asked|meant|wanted)",
    r"\bi (said|told you)\b",
    r"\bstop doing\b",
    r"\bdon'?t do that\b",
    r"\bwhy did you\b",
    r"\bagain\?",
]

REMINDER = (
    "The user may be correcting a mistake. If so: after fixing it, append one line to "
    ".claude/MEMORY.md: `- YYYY-MM-DD: <what went wrong> → <the rule>`. "
    "Skip if it is not a correction."
)


def main():
    prompt = json.load(sys.stdin).get("prompt", "")
    if any(re.search(p, prompt, re.IGNORECASE) for p in PATTERNS):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": REMINDER,
        }}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail open: never block the session
        print(f"mistake_saver hook error: {e}", file=sys.stderr)
    sys.exit(0)
