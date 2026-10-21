#!/usr/bin/env python3
"""Public repository admission guard.

Hard-blocks material that must never be published:
  * private keys, cloud/GitHub tokens
  * real environment files (only *.example / *.sample / *.template are allowed)
  * internal hand-over / pre-launch / design-delivery documents
  * build caches, database dumps, backups and local scratch files
  * public IPv4 addresses and hard-coded default test credentials

Warns (does not block) on legacy internal-ops wording that should move to the
private ops repository. Use ``--strict`` in a release checklist to turn warnings
into failures.

Usage:
    python .github/scripts/check_public_repo.py
    python .github/scripts/check_public_repo.py --strict
    python .github/scripts/check_public_repo.py --history
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
SKIP_CONTENT = {
    Path(".github/scripts/check_public_repo.py"),
    Path(".github/workflows/public-repo-guard.yml"),
    Path(".github/workflows/secret-history-audit.yml"),
}
# Governance docs legitimately mention forbidden wording while explaining the rules.
SKIP_WARNINGS = {
    Path("README.md"),
    Path("SECURITY.md"),
    Path("CONTRIBUTING.md"),
    Path(".github/pull_request_template.md"),
}
MAX_BYTES = 1_500_000

# Paths that are intentionally public even though the generic rule would match.
PATH_ALLOW = {
    "frontend/.env.production",  # build-time public URLs only; secrets are still content-scanned
}

HARD_PATH_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|/)\.env($|\.)", re.I), "real environment file (commit *.example instead)"),
    (re.compile(r"(^|/)(HANDOVER|HANDOFF|PRE_LAUNCH|BACKEND_HANDOFF)", re.I), "internal hand-over document"),
    (re.compile(r"(^|/)overview-task\d*\.md$", re.I), "internal task overview"),
    (re.compile(r"(^|/)crawlers?/VERIFICATION\.md$", re.I), "internal verification notes"),
    (re.compile(r"(^|/)prototype[ _-]?design", re.I), "private design-delivery artifact"),
    (re.compile(r"\.tsbuildinfo$", re.I), "TypeScript build cache"),
    (re.compile(r"\.(pem|key|p12|pfx|jks)$", re.I), "private key / certificate material"),
    (re.compile(r"(^|/)id_rsa", re.I), "SSH private key"),
    (re.compile(r"(^|/)(db\.sqlite3|.*\.sqlite3|.*\.dump|.*\.sql\.gz)$", re.I), "database dump"),
    (re.compile(r"\.(bak|bak-.+|orig|save|swp|old)$", re.I), "backup / editor scratch file"),
    (re.compile(r"(^|/)(keys|volumes|_shots|dist-verify|node_modules)/", re.I), "local runtime / build directory"),
    (re.compile(r"(^|/)(_pytest_out\.txt|_verify_.*|verify-e2e\.(py|mjs)|page_out\.html)$", re.I), "local scratch file"),
]

HARD_CONTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub fine-grained PAT"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "generic API key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "Google API key"),
    (re.compile(r"Test@\d{6}\b"), "default test password"),
    (re.compile(r"\btest1234\b"), "default demo password"),
]

WARN_CONTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"宝塔|BT-Panel|/www/wwwroot/|/opt/(?:rank|lotus-passport)|~?/\.acme\.sh"), "host/panel specific ops detail"),
    (re.compile(r"HANDOVER(?:\s*§|\.md)|HANDOFF(?:\s*§|\.md)|PRE_LAUNCH"), "reference to private hand-over document"),
    (re.compile(r"交付专家|Agent Prompt Guide|critique-reviewer|Anti-Slop"), "AI-agent delivery artifact"),
    (re.compile(r"本沙箱|受管沙箱|safe-delete"), "sandbox-specific workaround wording"),
    (re.compile(r"用户决策|与用户确认|经用户确认|两轮确认"), "agent work-log wording"),
    (re.compile(r"\b(?:TODO|FIXME|XXX|HACK)\b"), "unfinished marker"),
]

IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IP_CONTEXT_RE = re.compile(
    r"(?i)(?:\bip\b|\bhost\b|\bserver\b|\baddress\b|remote_addr|forwarded|https?://|\bsocket\b|\bbind\b|\bendpoint\b|服务器|地址)"
)
TEST_PATH_RE = re.compile(r"(^|/)(?:tests?|__tests__)/|(^|/)test_|\.test\.|\.spec\.")


def is_example_env(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1].lower()
    return name.startswith(".env") and name.endswith((".example", ".sample", ".template"))


def tracked_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    )
    return [ROOT / p for p in out.decode("utf-8", "replace").split("\0") if p]


def is_text(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_BYTES:
            return False
        chunk = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\0" not in chunk


def path_findings(files: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        if not path.exists():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in PATH_ALLOW or is_example_env(rel):
            continue
        for pattern, reason in HARD_PATH_RULES:
            if pattern.search(rel):
                findings.append(f"BLOCK {rel}: {reason}")
                break
    return findings


def content_findings(files: list[Path]) -> tuple[list[str], list[str]]:
    blocks: list[str] = []
    warns: list[str] = []
    for path in files:
        if not path.exists():
            continue
        rel = path.relative_to(ROOT)
        rel_posix = rel.as_posix()
        if rel in SKIP_CONTENT or not is_text(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            if len(line) > 4000:
                continue
            for pattern, reason in HARD_CONTENT_RULES:
                if pattern.search(line):
                    blocks.append(f"BLOCK {rel_posix}:{lineno}: {reason}")
            if rel not in SKIP_WARNINGS:
                for pattern, reason in WARN_CONTENT_RULES:
                    if pattern.search(line):
                        warns.append(f"WARN  {rel_posix}:{lineno}: {reason}")
            if not TEST_PATH_RE.search(rel_posix) and IP_CONTEXT_RE.search(line):
                for match in IPV4_RE.finditer(line):
                    try:
                        addr = ipaddress.ip_address(match.group(0))
                    except ValueError:
                        continue
                    if addr.is_global:
                        blocks.append(f"BLOCK {rel_posix}:{lineno}: public IPv4 address ({addr})")
    return blocks, warns


def history_findings() -> list[str]:
    """Check only tracked paths, not blob contents (use gitleaks for contents)."""
    out = subprocess.check_output(
        ["git", "-C", str(ROOT), "log", "--all", "--name-only", "--pretty=format:"],
        stderr=subprocess.DEVNULL,
    )
    seen = sorted({p for p in out.decode("utf-8", "replace").splitlines() if p.strip()})
    findings: list[str] = []
    for rel in seen:
        if is_example_env(rel) or rel in PATH_ALLOW:
            continue
        for pattern, reason in HARD_PATH_RULES:
            if pattern.search(rel):
                findings.append(f"BLOCK history:{rel}: {reason}")
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--history", action="store_true", help="check forbidden paths across all commits")
    args = parser.parse_args()

    files = tracked_files()
    blocks = path_findings(files)
    content_blocks, warns = content_findings(files)
    blocks += content_blocks
    if args.history:
        blocks += history_findings()

    for line in blocks:
        print(line)
    for line in warns:
        print(line)

    print(f"\nchecked {len(files)} tracked files; {len(blocks)} blocking, {len(warns)} warning(s)")
    if args.history:
        print("history mode: this is expected to fail until internal docs/secrets are purged from git history")
    if blocks or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
