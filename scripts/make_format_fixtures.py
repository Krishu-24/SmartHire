"""
Generate `fixtures/formats/` — the same candidate, laid out six different ways.

Every resume here describes ONE person with an identical skill set. That is the
whole point: a shortlisting engine that ranks the same human differently
depending on whether their CV used two columns or a table is not measuring the
human. `scripts/verify_formats.py` asserts the spread across these stays small.

The six shapes, chosen because each breaks a different assumption:

    classic      headed sections, one column          the happy path
    twocolumn    skills rail beside the body          raw reading order interleaves them
    nohead       no section headings at all           section weighting has nothing to read
    allcaps      ALL-CAPS decorated rules             `^Word$` header regex misses them
    inline       "Skills: Python, Java" on one line   header and body share a line
    prose        one continuous narrative             no lines, no bullets, no structure

    python scripts/make_format_fixtures.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _console  # noqa: F401  (configures stdout encoding on import)

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / "fixtures" / "formats"

# One person, six layouts. Same skills, same employers, same projects.
FACTS = {
    "name": "Rhea Kapoor",
    "email": "rhea.kapoor@email.com",
    "github": "github.com/rheakapoor",
    "city": "Pune, India",
    "degree": "B.Tech Computer Science, 2022 - 2026",
    "role": "Software Engineering Intern, Zerodha",
    "dates": "Jun 2025 - Nov 2025",
    "bullets": [
        "Built React dashboards consumed by 300+ internal users",
        "Developed Node.js services exposing REST APIs for trade reconciliation",
        "Wrote MongoDB aggregation pipelines powering analytics views",
        "Containerised the service with Docker and deployed to AWS",
        "Added Jest unit tests, raising coverage from 34% to 81%",
    ],
    "project": "LedgerLite - Full stack expense tracker",
    "project_bullets": [
        "React frontend with a Node.js and Express backend",
        "MongoDB for persistence, JWT authentication, REST API contract",
        "CI pipeline running Jest on every push, deployed via Docker",
    ],
    "skills": "JavaScript, TypeScript, React, Node.js, Express, MongoDB, SQL",
    "skills2": "Git, Docker, AWS, Jest, HTML, CSS, Agile",
}


def _page(doc):
    return doc.new_page(width=595, height=842)          # A4


def _wrap(text: str, size: float, width: float) -> list[str]:
    """Greedy wrap at an approximate Helvetica advance width."""
    budget = max(int(width / (size * 0.50)), 12)
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= budget:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _write(page, x, y, text, size=10, bold=False, width=460):
    """Draw one (wrapped) run of text and return the next baseline.

    `insert_text` with the base-14 aliases rather than `insert_textbox`: this
    PyMuPDF build rejects "helvB" and wants an embedded font file for anything it
    does not recognise, and base-14 keeps these fixtures dependency-free.
    """
    font = "hebo" if bold else "helv"
    for line in _wrap(text, size, width):
        page.insert_text((x, y), line, fontsize=size, fontname=font)
        y += size + 3.2
    return y


def classic(path: pathlib.Path) -> None:
    doc = pymupdf.open()
    p = _page(doc)
    y = 60
    y = _write(p, 60, y, FACTS["name"], 16, True)
    y = _write(p, 60, y, f"{FACTS['city']} | {FACTS['email']} | {FACTS['github']}", 9)
    y += 10
    y = _write(p, 60, y, "EDUCATION", 11, True)
    y = _write(p, 60, y, FACTS["degree"], 10)
    y += 8
    y = _write(p, 60, y, "EXPERIENCE", 11, True)
    y = _write(p, 60, y, FACTS["role"], 10, True)
    y = _write(p, 60, y, FACTS["dates"], 9)
    for b in FACTS["bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 8
    y = _write(p, 60, y, "PROJECTS", 11, True)
    y = _write(p, 60, y, FACTS["project"], 10, True)
    for b in FACTS["project_bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 8
    y = _write(p, 60, y, "SKILLS", 11, True)
    y = _write(p, 60, y, FACTS["skills"], 10)
    y = _write(p, 60, y, FACTS["skills2"], 10)
    doc.save(path)
    doc.close()


def twocolumn(path: pathlib.Path) -> None:
    """Narrow skills rail on the left, body on the right — the classic ATS-breaker."""
    doc = pymupdf.open()
    p = _page(doc)

    ly = 60
    ly = _write(p, 45, ly, FACTS["name"], 14, True, width=150)
    ly = _write(p, 45, ly, FACTS["city"], 8, width=150)
    ly = _write(p, 45, ly, FACTS["email"], 8, width=150)
    ly = _write(p, 45, ly, FACTS["github"], 8, width=150)
    ly += 12
    ly = _write(p, 45, ly, "SKILLS", 10, True, width=150)
    for chunk in (FACTS["skills"] + ", " + FACTS["skills2"]).split(", "):
        ly = _write(p, 45, ly, chunk, 9, width=150)
    ly += 10
    ly = _write(p, 45, ly, "EDUCATION", 10, True, width=150)
    ly = _write(p, 45, ly, FACTS["degree"], 9, width=150)

    ry = 60
    ry = _write(p, 250, ry, "EXPERIENCE", 11, True, width=300)
    ry = _write(p, 250, ry, FACTS["role"], 10, True, width=300)
    ry = _write(p, 250, ry, FACTS["dates"], 9, width=300)
    for b in FACTS["bullets"]:
        ry = _write(p, 250, ry, f"- {b}", 9.5, width=300)
    ry += 10
    ry = _write(p, 250, ry, "PROJECTS", 11, True, width=300)
    ry = _write(p, 250, ry, FACTS["project"], 10, True, width=300)
    for b in FACTS["project_bullets"]:
        ry = _write(p, 250, ry, f"- {b}", 9.5, width=300)

    doc.save(path)
    doc.close()


def nohead(path: pathlib.Path) -> None:
    """No section headings whatsoever — just blocks separated by blank lines."""
    doc = pymupdf.open()
    p = _page(doc)
    y = 60
    y = _write(p, 60, y, FACTS["name"], 15, True)
    y = _write(p, 60, y, f"{FACTS['city']} | {FACTS['email']} | {FACTS['github']}", 9)
    y += 14
    y = _write(p, 60, y, FACTS["degree"], 10)
    y += 12
    y = _write(p, 60, y, f"{FACTS['role']}, {FACTS['dates']}", 10, True)
    for b in FACTS["bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 12
    y = _write(p, 60, y, FACTS["project"], 10, True)
    for b in FACTS["project_bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 12
    y = _write(p, 60, y, FACTS["skills"], 10)
    y = _write(p, 60, y, FACTS["skills2"], 10)
    doc.save(path)
    doc.close()


def allcaps(path: pathlib.Path) -> None:
    """ALL-CAPS headings wrapped in rules, which a `^Word$` regex never matches."""
    doc = pymupdf.open()
    p = _page(doc)
    y = 60
    y = _write(p, 60, y, FACTS["name"].upper(), 16, True)
    y = _write(p, 60, y, f"{FACTS['city']}  *  {FACTS['email']}  *  {FACTS['github']}", 9)
    y += 10
    for title, body in [
        ("EDUCATION", [FACTS["degree"]]),
        ("PROFESSIONAL EXPERIENCE",
         [FACTS["role"], FACTS["dates"]] + [f"- {b}" for b in FACTS["bullets"]]),
        ("KEY PROJECTS",
         [FACTS["project"]] + [f"- {b}" for b in FACTS["project_bullets"]]),
        ("TECHNICAL SKILLS", [FACTS["skills"], FACTS["skills2"]]),
    ]:
        y = _write(p, 60, y, f"---------- {title} ----------", 11, True)
        for line in body:
            y = _write(p, 60, y, line, 10)
        y += 8
    doc.save(path)
    doc.close()


def inline(path: pathlib.Path) -> None:
    """Heading and body share a line: "Skills: Python, Java"."""
    doc = pymupdf.open()
    p = _page(doc)
    y = 60
    y = _write(p, 60, y, FACTS["name"], 15, True)
    y = _write(p, 60, y, f"{FACTS['city']} | {FACTS['email']} | {FACTS['github']}", 9)
    y += 12
    y = _write(p, 60, y, f"Education: {FACTS['degree']}", 10)
    y += 6
    y = _write(p, 60, y, f"Experience: {FACTS['role']}, {FACTS['dates']}", 10)
    for b in FACTS["bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 6
    y = _write(p, 60, y, f"Projects: {FACTS['project']}", 10)
    for b in FACTS["project_bullets"]:
        y = _write(p, 66, y, f"- {b}", 10)
    y += 6
    y = _write(p, 60, y, f"Skills: {FACTS['skills']}, {FACTS['skills2']}", 10)
    doc.save(path)
    doc.close()


def prose(path: pathlib.Path) -> None:
    """One continuous narrative. No bullets, no headings, no dates on their own line."""
    text = (
        f"{FACTS['name']} - {FACTS['city']} - {FACTS['email']} - {FACTS['github']}. "
        f"I am a final year computer science student ({FACTS['degree']}) who has spent "
        f"the last two years building web applications. From {FACTS['dates']} I interned "
        f"at Zerodha as a Software Engineering Intern, where I built React dashboards "
        f"consumed by over 300 internal users and developed Node.js services exposing "
        f"REST APIs for trade reconciliation. I wrote MongoDB aggregation pipelines that "
        f"power their analytics views, containerised the service with Docker and deployed "
        f"it to AWS, and added Jest unit tests that raised coverage from 34 percent to 81 "
        f"percent. Alongside that I built LedgerLite, a full stack expense tracker with a "
        f"React frontend and a Node.js and Express backend, using MongoDB for persistence "
        f"and JWT for authentication, with a CI pipeline running Jest on every push and "
        f"deployment through Docker. Day to day I work in JavaScript and TypeScript, and "
        f"I am comfortable with SQL, Git, AWS, HTML, CSS and working in an Agile team."
    )
    doc = pymupdf.open()
    p = _page(doc)
    _write(p, 60, 60, text, 10.5, width=475)
    doc.save(path)
    doc.close()


BUILDERS = {
    "classic": classic,
    "twocolumn": twocolumn,
    "nohead": nohead,
    "allcaps": allcaps,
    "inline": inline,
    "prose": prose,
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, build in BUILDERS.items():
        path = DEST / f"{name}.pdf"
        build(path)
        print(f"  wrote {path.relative_to(ROOT)}")
    print(f"\n{len(BUILDERS)} format fixtures in {DEST.relative_to(ROOT)}")
    print("Same candidate, same skills, six layouts. Check them with:")
    print("    python scripts/verify_formats.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
