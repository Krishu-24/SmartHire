"""
Credential loading, with the rules that keep a token out of the repository.

The GitHub token is the only secret SmartHire has, and it is the kind of secret
people leak: it lives in a launcher script they edit, and the launcher is the
file most likely to be committed. So the contract here is deliberately narrow.

  * The token is read from the environment, or from a `.env` file that
    `.gitignore` already excludes. It is never read from a tracked file, and
    `run.bat` / `run.command` write it to `.env` rather than to themselves.

  * `mask()` is the only way a token is ever printed. Nothing in the codebase
    logs `GITHUB_TOKEN` directly, and the launchers echo the masked form.

  * `looks_valid()` catches the two failures that otherwise present as a silent
    403 an hour later: a placeholder never replaced, and a token pasted with
    quotes or whitespace around it.

A token with no scopes is enough for everything SmartHire does — it only reads
public repositories. `advice()` says so, because the natural instinct when
creating one is to tick every box.
"""
from __future__ import annotations

import os
import pathlib
import re

# GitHub's documented prefixes. `ghp_` is a classic PAT, `github_pat_` a
# fine-grained one; the others appear when someone pastes the wrong token type.
_KNOWN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")

# Values people leave behind when they copy an example file without editing it.
_PLACEHOLDERS = frozenset({
    "", "ghp_your_token_here", "your_token_here", "yourtokenhere",
    "xxx", "changeme", "todo", "none", "null", "<token>", "ghp_xxx",
})


def load_dotenv(path: pathlib.Path) -> dict[str, str]:
    """Read a `.env` file into a dict. Never raises, never overwrites the environment.

    A hand-rolled parser rather than a dependency: the format we need is
    `KEY=value` with optional quotes and `#` comments, and a launcher-written
    file is the only thing that ever produces it. Values already present in the
    real environment win, so `set GITHUB_TOKEN=... && run.bat` still overrides
    the file.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip one matched pair of quotes; a token never legitimately contains them.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def apply_dotenv(path: pathlib.Path) -> list[str]:
    """Load `.env` into os.environ without clobbering what is already set.

    Returns the names of the keys it supplied, so a caller can report where a
    credential came from without ever touching the value.
    """
    applied: list[str] = []
    for key, value in load_dotenv(path).items():
        if key not in os.environ and value:
            os.environ[key] = value
            applied.append(key)
    return applied


def clean(token: str | None) -> str:
    """Normalise a token as typed: surrounding whitespace and quotes removed."""
    if not token:
        return ""
    return token.strip().strip("\"'").strip()


def looks_valid(token: str | None) -> bool:
    """True when this could plausibly be a real GitHub token.

    Deliberately shape-only — the network decides whether it actually works.
    The job here is to catch an unedited placeholder before it becomes a
    confusing rate-limit error.
    """
    value = clean(token)
    if value.lower() in _PLACEHOLDERS:
        return False
    if len(value) < 20:
        return False
    if re.search(r"\s", value):
        return False
    # A modern token carries a known prefix. Older 40-char hex tokens still work,
    # so accept those too rather than rejecting a credential that is genuinely fine.
    return value.startswith(_KNOWN_PREFIXES) or bool(re.fullmatch(r"[0-9a-f]{40}", value))


def mask(token: str | None) -> str:
    """The only safe way to show a token. `ghp_1234…cdef` — enough to identify, not to use."""
    value = clean(token)
    if not value:
        return "(not set)"
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:7]}…{value[-4:]}"


def describe(token: str | None) -> str:
    """One line about the credential, for a launcher or a health endpoint."""
    value = clean(token)
    if not value:
        return "no GitHub token — public API capped at 60 requests/hour"
    if not looks_valid(value):
        return f"GitHub token {mask(value)} does not look like a real token — check .env"
    return f"GitHub token {mask(value)} loaded — 5000 requests/hour"


def advice() -> str:
    """What to create, and — more usefully — what not to tick."""
    return (
        "Create one at https://github.com/settings/tokens with NO scopes ticked. "
        "SmartHire only reads public repositories, so a token with zero "
        "permissions works and leaks nothing if it escapes."
    )
