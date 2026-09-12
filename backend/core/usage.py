"""
Is the library imported, or is it actually used?

A dependency manifest proves someone typed a package name into a file. It does
not prove they wrote a line of code with it — `package.json` accumulates things
a tutorial added two years ago, and `import pandas as pd` at the top of a script
that never touches `pd` is a copied header, not a skill.

So this module reads the source and asks the next question: after the import,
does the imported name appear again, and does it appear in a position that means
something happened — a call, an attribute access, a JSX tag, a decorator?

Three verdicts:

    CALLED     imported and invoked          `pd.read_csv(...)`, `<Router>`, `app.use(x)`
    REFERENCED imported and mentioned        passed around, re-exported, type-only
    IMPORTED   imported and never seen again the copied header

Only CALLED is treated as strong evidence. REFERENCED still counts, at a lower
weight, because a type-only TypeScript import is real usage. IMPORTED is
recorded and deliberately given nothing: it is exactly the shape of a dependency
that was never a skill.

Regex rather than a real parser, and that is a deliberate limit. We are reading
five languages off a network in a hackathon budget; a tree-sitter grammar per
language would be more correct and would not change a single ranking, because
the question "does this identifier appear again in a call position" survives
approximate parsing. Where it is unsure it degrades to REFERENCED, never to a
false CALLED.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CALLED = "CALLED"
REFERENCED = "REFERENCED"
IMPORTED = "IMPORTED"

# What each verdict is worth, multiplying the evidence this import provides.
VERDICT_WEIGHT = {CALLED: 1.0, REFERENCED: 0.6, IMPORTED: 0.0}

SOURCE_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".java", ".rb")


@dataclass(slots=True)
class ImportUse:
    """One import in one file, and what became of it."""
    module: str                 # the package as written: "pandas", "@apollo/client"
    alias: str                  # the local name bound: "pd", "useQuery", "express"
    verdict: str
    file: str
    evidence: str = ""          # the line that proves use, trimmed

    @property
    def weight(self) -> float:
        return VERDICT_WEIGHT.get(self.verdict, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Import extraction
# ─────────────────────────────────────────────────────────────────────────────

# Python:  import x            import x as y        from x import a, b as c
_PY_IMPORT = re.compile(
    r"^\s*import\s+([A-Za-z_][\w.]*)(?:\s+as\s+([A-Za-z_]\w*))?", re.M)
_PY_FROM = re.compile(
    r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+(.+)$", re.M)

# JS/TS:   import x from 'm'   import {a, b as c} from 'm'   import * as ns from 'm'
_JS_IMPORT = re.compile(
    r"""^\s*import\s+(?:(?P<default>[A-Za-z_$][\w$]*)\s*,?\s*)?"""
    r"""(?:\*\s+as\s+(?P<ns>[A-Za-z_$][\w$]*)\s*)?"""
    r"""(?:\{(?P<named>[^}]*)\}\s*)?"""
    r"""(?:from\s+)?['"](?P<mod>[^'"]+)['"]""",
    re.M | re.X,
)
_JS_REQUIRE = re.compile(
    r"""(?:const|let|var)\s+(?P<bind>\{[^}]*\}|[A-Za-z_$][\w$]*)\s*=\s*"""
    r"""require\(\s*['"](?P<mod>[^'"]+)['"]\s*\)""",
    re.M,
)

_NAMED_RE = re.compile(r"([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?")


def _bindings(text: str, path: str) -> list[tuple[str, str]]:
    """Every (module, local_name) this file imports."""
    out: list[tuple[str, str]] = []
    lower = path.lower()

    if lower.endswith(".py"):
        for m in _PY_IMPORT.finditer(text):
            module, alias = m.group(1), m.group(2)
            out.append((module.split(".")[0], alias or module.split(".")[0]))
        for m in _PY_FROM.finditer(text):
            module, names = m.group(1), m.group(2)
            root = module.split(".")[0]
            for part in names.split(","):
                nm = _NAMED_RE.search(part.strip())
                if nm:
                    out.append((root, nm.group(2) or nm.group(1)))
        return out

    if lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
        for m in _JS_IMPORT.finditer(text):
            module = m.group("mod")
            if not module:
                continue
            for name in (m.group("default"), m.group("ns")):
                if name:
                    out.append((module, name))
            named = m.group("named") or ""
            for part in named.split(","):
                nm = _NAMED_RE.search(part.strip())
                if nm:
                    out.append((module, nm.group(2) or nm.group(1)))
            # A bare `import 'some.css'` binds nothing but is still real usage.
            if not any(m.group(g) for g in ("default", "ns", "named")):
                out.append((module, ""))
        for m in _JS_REQUIRE.finditer(text):
            module, bind = m.group("mod"), m.group("bind")
            if bind.startswith("{"):
                for part in bind.strip("{}").split(","):
                    nm = _NAMED_RE.search(part.strip())
                    if nm:
                        out.append((module, nm.group(2) or nm.group(1)))
            else:
                out.append((module, bind))
        return out

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Usage detection
# ─────────────────────────────────────────────────────────────────────────────

def _usage_patterns(alias: str) -> list[re.Pattern[str]]:
    """Positions that mean the name was actually exercised."""
    a = re.escape(alias)
    return [
        re.compile(rf"(?<![\w.]){a}\s*\("),        # call:        pd(...)  express()
        re.compile(rf"(?<![\w.]){a}\s*\."),        # attribute:   pd.read_csv
        re.compile(rf"<\s*{a}[\s/>]"),             # JSX element: <Router>
        re.compile(rf"(?<![\w.])@{a}(?![\w])"),    # decorator:   @app
        re.compile(rf"(?<![\w.]){a}\s*\["),        # subscript:   router["x"]
        re.compile(rf"(?<![\w.]){a}\s*`"),         # tagged tpl:  styled`...`
    ]


def analyse_file(text: str, path: str) -> list[ImportUse]:
    """Classify every import in one source file."""
    if not text or not path.lower().endswith(SOURCE_EXTENSIONS):
        return []

    lines = text.splitlines()
    # Import lines are excluded from the usage search, or every import would
    # trivially "use" itself.
    body_lines = [
        ln for ln in lines
        if not re.match(r"^\s*(import\b|from\b.+\bimport\b|(?:const|let|var)\s+.*require\()", ln)
    ]
    body = "\n".join(body_lines)

    out: list[ImportUse] = []
    seen: set[tuple[str, str]] = set()

    for module, alias in _bindings(text, path):
        if (module, alias) in seen:
            continue
        seen.add((module, alias))

        # A side-effect import (`import './styles.css'`) binds no name; the
        # import IS the use.
        if not alias:
            out.append(ImportUse(module, "", CALLED, path, "side-effect import"))
            continue

        verdict, evidence = IMPORTED, ""
        for pattern in _usage_patterns(alias):
            hit = pattern.search(body)
            if hit:
                verdict = CALLED
                line = body[:hit.start()].count("\n")
                evidence = body_lines[line].strip()[:120] if line < len(body_lines) else ""
                break
        else:
            # Mentioned but never in a call position: a re-export, a type, or a
            # value passed onward. Real, but weaker.
            if re.search(rf"(?<![\w.]){re.escape(alias)}(?![\w])", body):
                verdict = REFERENCED

        out.append(ImportUse(module, alias, verdict, path, evidence))

    return out


def summarise(uses: list[ImportUse]) -> dict[str, ImportUse]:
    """Best verdict per module across every file that imported it.

    One file copying a header does not erase another file using the library
    properly, so the strongest verdict wins.
    """
    best: dict[str, ImportUse] = {}
    order = {CALLED: 2, REFERENCED: 1, IMPORTED: 0}
    for use in uses:
        current = best.get(use.module)
        if current is None or order[use.verdict] > order[current.verdict]:
            best[use.module] = use
    return best
