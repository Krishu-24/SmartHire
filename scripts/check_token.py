"""
Report on the GitHub token, and optionally save one — without ever printing it.

Called by run.bat / run.command. Exit codes are the interface:

    0   a usable token is configured
    2   no token (or a placeholder) — the launcher may offer to capture one
    1   a token is present but malformed, so the launcher should say so loudly

    python scripts/check_token.py
    python scripts/check_token.py --save ghp_xxxxxxxx
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _console  # noqa: F401  (configures stdout encoding on import)

from backend import credentials

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def save(token: str) -> int:
    """Write the token into .env, replacing any existing GITHUB_TOKEN line.

    Writes to `.env` and nowhere else. The launchers are tracked files; a
    credential written into one of those is a credential that gets committed.
    """
    token = credentials.clean(token)

    if not credentials.looks_valid(token):
        print(f"  [!] That does not look like a GitHub token ({credentials.mask(token)}).")
        print(f"      {credentials.advice()}")
        return 1

    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines()

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("GITHUB_TOKEN=") or line.strip().startswith("export GITHUB_TOKEN="):
            lines[i] = f"GITHUB_TOKEN={token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"GITHUB_TOKEN={token}")

    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # Best effort on POSIX: make the file owner-only. Windows inherits the
    # directory ACL and has no chmod equivalent worth emulating here.
    try:
        ENV_PATH.chmod(0o600)
    except (OSError, NotImplementedError):
        pass

    print(f"  [OK] Saved to .env ({credentials.mask(token)}). This file is gitignored.")
    return 0


def report() -> int:
    token = credentials.clean(
        credentials.load_dotenv(ENV_PATH).get("GITHUB_TOKEN")
        or __import__("os").environ.get("GITHUB_TOKEN", "")
    )

    if not token:
        print("  [i ] No GitHub token. Live lookups are capped at 60 requests/hour,")
        print("       which is not enough for a full pool. The bundled synthetic")
        print("       profiles still demonstrate the feature offline.")
        print(f"       {credentials.advice()}")
        return 2

    if not credentials.looks_valid(token):
        print(f"  [!] GITHUB_TOKEN is set but malformed ({credentials.mask(token)}).")
        print("      Check .env for stray quotes, spaces, or an unedited placeholder.")
        return 1

    print(f"  [OK] {credentials.describe(token)}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--save":
        return save(argv[1])
    return report()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
