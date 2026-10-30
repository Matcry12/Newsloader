#!/usr/bin/env python3
"""PreToolUse(Bash): deny secret reads, ask on dangerous commands, vet `git commit`.

# ponytail: the command is split on && || ; | (quote-aware via shlex). Subshells, $(...),
# backticks, `bash -c "..."`, aliases and `git add . && git commit` (staged state is read
# before the add runs) and `git commit -a` are NOT seen. It's a seatbelt, not a sandbox.
"""
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULTS = {"max_file_mb": 10, "venv_guard": False, "protected_branches": ["main", "master"]}

SAFE_RM_DIRS = {"tmp", "cache", ".cache", "__pycache__", "node_modules", "dist", "build",
                ".pytest_cache", ".ruff_cache", ".next", "target", ".venv", "venv", "coverage",
                "out", ".turbo", ".mypy_cache", ".tox", ".parcel-cache"}

WRAPPERS = {"sudo", "env", "command", "nohup", "time", "nice", "exec", "xargs"}

SECRET_PATTERNS = [
    ("sk- key", r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    ("sk-ant- key", r"(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{20,}"),
    ("hf_ token", r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{30,}"),
    ("AWS access key", r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    ("GitHub token", r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{36}"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("key/secret/token/password assignment",
     r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
]

ENV_NAME = r"\.env(\.[\w.-]+)?"
ENV_OK_SUFFIX = (".example", ".sample", ".template")


def decide(kind, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": kind,
        "permissionDecisionReason": reason,
    }}))


def load_config(project):
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(project, ".claude", "harness.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def parse(cmd):
    """Return a list of (operator_before, tokens) segments."""
    cmd = cmd.replace("\\\n", " ")  # line continuation
    # drop heredoc bodies: their text is data, not commands
    cmd = re.sub(r"(<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n).*?\n[ \t]*\2[ \t]*(?=\n|$)", r"\1", cmd, flags=re.S)
    cmd = cmd.replace("\n", " ; ")
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:  # unbalanced quotes: crude fallback
        toks = []
        for part in re.split(r"(&&|\|\||;|\|)", cmd):
            toks += [part] if part in ("&&", "||", ";", "|") else part.split()
    segs, op, cur = [], "", []
    for t in toks:
        if re.fullmatch(r"[;&|()]+", t):
            if cur:
                segs.append((op, cur))
            op, cur = t, []
        else:
            cur.append(t)
    if cur:
        segs.append((op, cur))
    return segs


def words_of(toks):
    """(has_sudo, command words) with VAR=x assignments and wrapper commands (sudo, env, ...) stripped."""
    sudo = wrapped = False
    i = 0
    while i < len(toks):
        t = toks[i]
        name = os.path.basename(t)
        if re.fullmatch(r"\w+=.*", t):
            pass
        elif name in WRAPPERS:
            sudo |= name == "sudo"
            wrapped = True
        elif not (wrapped and (t.startswith("-") or t.isdigit())):
            break
        i += 1
    return sudo, toks[i:]


def is_env_name(base):
    return bool(re.fullmatch(ENV_NAME, base)) and not base.endswith(ENV_OK_SUFFIX)


def is_secret_path(tok):
    for c in {tok, tok.lstrip("<@"), re.split("[=@]", tok)[-1]}:
        base = c.rstrip("/").rsplit("/", 1)[-1]
        if ((not re.search(r"\s", c) and re.search(r"(^|/)\.(ssh|aws)(/|$)", c)) or is_env_name(base)
                or base.endswith(".pem") or base in ("id_rsa", "id_ed25519")):
            return True
    return False


def secret_args(words):
    """Args of one command that could read a secret file (see exemptions below)."""
    cmd, args = os.path.basename(words[0]), words[1:]
    if cmd in ("echo", "printf"):
        return []
    if cmd in ("grep", "egrep", "fgrep", "rg"):  # first non-flag arg is the pattern
        i = next((i for i, a in enumerate(args) if not a.startswith("-")), None)
        args = args[:i] + args[i + 1:] if i is not None else args
    elif cmd in ("cp", "mv"):  # writing TO a secret file is fine, only sources count
        plain = [a for a in args if not a.startswith("-")]
        args = [a for a in args if a.startswith("-")] + plain[:-1]
    elif cmd == "git" and git_parts(words)[0] == "commit":  # skip the commit message
        out, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a == "--message" or re.fullmatch(r"-[A-Za-z]*m", a):
                skip = True
            elif not (a.startswith("--message=") or re.match(r"-m.", a)):
                out.append(a)
        args = out
    return [a for i, a in enumerate(args) if not (i and args[i - 1] in (">", ">>", ">|"))]


def short_flags(args):
    return "".join(a[1:] for a in args if re.fullmatch(r"-[A-Za-z]+", a))


def rm_is_risky(args):
    flags = short_flags(args)
    recursive = "r" in flags or "R" in flags or "--recursive" in args
    force = "f" in flags or "--force" in args
    if not (recursive and force):
        return False
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        return True
    for t in targets:
        parts = [p for p in t.split("/") if p not in ("", ".")]
        # safe only if relative, no .. and the FIRST component is a throwaway dir
        if t.startswith(("/", "~")) or "$" in t or ".." in parts or not parts or parts[0] not in SAFE_RM_DIRS:
            return True
    return False


def git_parts(words):
    """For `git [-C x] sub args...` return (sub, args) else (None, [])."""
    if not words or os.path.basename(words[0]) != "git":
        return None, []
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in ("-C", "-c") else 1
    return (words[i], words[i + 1:]) if i < len(words) else (None, [])


def ask_reason(prev, words, sudo):
    """Return the name of the dangerous rule matched by one segment, or None."""
    if sudo:
        return "sudo"
    if not words:
        return None
    cmd, args = os.path.basename(words[0]), words[1:]
    if cmd == "rm" and rm_is_risky(args):
        return "recursive force rm outside tmp/cache/build dirs"
    if cmd == "dd":
        return "dd"
    if cmd.startswith("mkfs"):
        return "mkfs"
    if cmd == "chmod" and "-R" in args and "777" in args:
        return "chmod -R 777"
    for i, a in enumerate(args):
        if a in (">", ">>") and i + 1 < len(args) and args[i + 1].startswith("/dev/sd"):
            return "redirect to /dev/sd*"
    sub, gargs = git_parts(words)
    if sub == "push" and ("f" in short_flags(gargs) or any(
            a in ("--delete", "-d") or a.startswith(("--force", "+", ":")) for a in gargs)):
        return "git push --force/delete"
    if sub == "reset" and "--hard" in gargs:
        return "git reset --hard"
    if sub == "clean" and ("f" in short_flags(gargs) or "--force" in gargs):
        return "git clean -f"
    staged_only = "--staged" in gargs and "--worktree" not in gargs
    if (sub == "checkout" and "." in gargs) or (sub == "restore" and "." in gargs and not staged_only):
        return "discarding all working-tree changes"
    if sub == "stash" and gargs[:1] in (["drop"], ["clear"]):
        return "git stash drop/clear"
    if sub == "branch" and "-D" in gargs:
        return "git branch -D"
    if cmd in ("sh", "bash", "zsh") and prev and os.path.basename(prev[0]) in ("curl", "wget"):
        return "piping curl/wget into a shell"
    return None


def run_git(project, *args):
    r = subprocess.run(["git", *args], cwd=project, capture_output=True, timeout=10)
    return r.stdout.decode("utf-8", "replace")


def commit_findings(project, cfg, deny, ask):
    """Append deny/ask reasons for a `git commit` about to run."""
    branch = run_git(project, "branch", "--show-current").strip()
    if branch in cfg["protected_branches"]:
        ask.append(f"committing directly to {branch}")

    names = [n for n in run_git(project, "diff", "--cached", "--name-only", "-z").split("\0") if n]
    limit = cfg["max_file_mb"] * 1024 * 1024
    for n in names:
        if is_secret_path(n):
            deny.append(f"staged file {n} looks like a secrets file; unstage it and add it to .gitignore")
        try:
            if os.path.getsize(os.path.join(project, n)) > limit:
                deny.append(f"staged file {n} is larger than {cfg['max_file_mb']} MB; "
                            "unstage it and add it to .gitignore")
        except OSError:
            pass

    current = "?"
    for line in run_git(project, "diff", "--cached", "-U0", "--no-color").splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
        elif line.startswith("+"):
            for label, pat in SECRET_PATTERNS:
                if re.search(pat, line[1:]):
                    deny.append(f"possible secret in staged {current} ({label}); never commit it")
                    break


def main():
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    cfg = load_config(project)

    deny, ask = [], []
    prev = None
    committing = False
    venv = cfg["venv_guard"] and os.path.isdir(os.path.join(project, ".venv")) \
        and ".venv/bin/activate" not in cmd
    for op, toks in parse(cmd):
        sudo, words = words_of(toks)
        if words and any(is_secret_path(t) for t in secret_args(words)):
            deny.append("command touches secrets (.env, ~/.ssh, ~/.aws, *.pem, private keys)")
        reason = ask_reason(prev if op == "|" else None, words, sudo)
        if reason:
            ask.append(reason)
        if git_parts(words)[0] == "commit":
            committing = True
        if venv and words:
            args = words[1:]
            if (words[0] in ("pip", "pip3") and "install" in args) or (
                    words[0] in ("python", "python3") and args[:2] == ["-m", "pip"] and "install" in args):
                deny.append("use .venv/bin/pip (a .venv exists)")
        prev = words

    if committing:
        try:
            commit_findings(project, cfg, deny, ask)
        except Exception as e:  # git failure/timeout: keep what we already found
            print(f"bash_guard: commit checks incomplete: {e}", file=sys.stderr)

    if deny:
        decide("deny", "; ".join(dict.fromkeys(deny)))
    elif ask:
        decide("ask", "Dangerous command: " + "; ".join(dict.fromkeys(ask)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail open: never block the session
        print(f"bash_guard hook error: {e}", file=sys.stderr)
    sys.exit(0)
