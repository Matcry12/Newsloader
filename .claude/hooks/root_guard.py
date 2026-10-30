#!/usr/bin/env python3
"""PreToolUse(Write): block creating new files directly in the project root."""
import json
import os
import sys

ROOT_ALLOW = ["README.md", "CLAUDE.md", "pyproject.toml", "requirements.txt", "package.json",
              ".gitignore", ".env.example", "LICENSE", "Makefile", "uv.lock", "package-lock.json"]


def main():
    data = json.load(sys.stdin)
    project = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    try:
        with open(os.path.join(project, ".claude", "harness.json"), encoding="utf-8") as f:
            allow = json.load(f).get("root_allow", ROOT_ALLOW)
    except (OSError, ValueError, AttributeError):  # unreadable file, bad JSON, or not an object
        allow = ROOT_ALLOW
    if not isinstance(allow, list):
        allow = ROOT_ALLOW

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return
    path = os.path.join(project, path)  # no-op when path is already absolute
    path = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
    name = os.path.basename(path)
    # ponytail: any dotfile is allowed (.gitignore, .env.example, configs); only plain names are policed
    if os.path.dirname(path) != project or os.path.exists(path) or name in allow or name.startswith("."):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "New files don't go in the project root. Put it in the matching folder "
                                    "(see CLAUDE.md Layout), or add it to root_allow in .claude/harness.json.",
    }}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail open: never block the session
        print(f"root_guard hook error: {e}", file=sys.stderr)
    sys.exit(0)
