"""Check files Git would publish for local data and common credential literals."""

import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    "work/", "legacy/", "outputs/SpirePilotApp/", "outputs/hybrid/runs/",
    "outputs/hybrid/experience/", "outputs/hybrid/smoke_test/",
    "outputs/hybrid/mod/",
)
FORBIDDEN_FILES = {
    "outputs/hybrid/config.json", "outputs/hybrid/desktop_process.json",
    "outputs/hybrid/STOP", "outputs/hybrid/controller.lock",
}
FORBIDDEN_SUFFIXES = (".sqlite3", ".jsonl", ".log", ".dll", ".pdb")
SECRET_PATTERNS = {
    "OpenRouter key": re.compile(r"sk-or-v1-[A-Za-z0-9_-]{20,}"),
    "API key": re.compile(r"sk-[A-Za-z0-9_-]{30,}"),
    "GitHub token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "local user path": re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+"),
}
BINARY_SUFFIXES = {".png", ".ico", ".jpg", ".jpeg", ".webp", ".dll", ".pdb", ".zip"}


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    staged_paths = [path.decode("utf-8") for path in tracked.split(b"\0") if path]
    new_paths = [path.decode("utf-8") for path in untracked.split(b"\0") if path]
    if not staged_paths and not new_paths:
        print("No publishable files found.", file=sys.stderr)
        return 1
    problems = []
    for name in staged_paths + new_paths:
        if (name in FORBIDDEN_FILES or name.startswith(FORBIDDEN_PREFIXES)
                or name.endswith(FORBIDDEN_SUFFIXES)):
            problems.append(f"local data in Git index: {name}")
            continue
        path = ROOT / name
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            data = (subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
                    if name in staged_paths else path.read_bytes())
            content = data.decode("utf-8")
        except (UnicodeDecodeError, OSError, subprocess.CalledProcessError):
            problems.append(f"unreadable tracked text file: {name}")
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                problems.append(f"possible {label}: {name}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Checked {len(staged_paths) + len(new_paths)} publishable files; no local data or known key patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
