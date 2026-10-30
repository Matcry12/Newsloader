#!/usr/bin/env python3
"""SessionStart: print the mistakes log and a short git summary."""
import json
import os
import subprocess
import sys


def git(project, *args):
    r = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=5)
    return r.returncode, r.stdout.strip()


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()

    mem = os.path.join(project, ".claude", "MEMORY.md")
    if os.path.isfile(mem):
        with open(mem, encoding="utf-8", errors="replace") as f:
            print(f.read().rstrip() + "\n")

    try:
        git_summary(project)
    except Exception as e:  # memory is already printed; a git failure must not lose it
        print(f"git: unavailable ({e})")


def git_summary(project):
    code, _ = git(project, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        print("git: not a repository")
        return
    _, branch = git(project, "branch", "--show-current")
    code, last = git(project, "log", "-1", "--format=%h %s (%cr)")
    _, status = git(project, "status", "--short")
    lines = status.splitlines()
    print(f"git branch: {branch or '(detached)'}")
    print(f"last commit: {last if code == 0 else '(none yet)'}")
    print(f"changed files: {len(lines)}")
    for line in lines[:10]:
        print(f"  {line}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail open: never block the session
        print(f"session_start hook error: {e}", file=sys.stderr)
    sys.exit(0)
