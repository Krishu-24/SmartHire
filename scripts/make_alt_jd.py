"""
Render a second job description, so the "swap the JD" path has somewhere to go.

Deliberately a different shape of role from `jd_technova.pdf`: Python, data and
infrastructure rather than the JavaScript full-stack set. Pointing the same pool
at this one should visibly re-rank it — the backend-leaning candidates rise and
the React-only ones fall — which is the whole point of being able to re-target a
pool without re-uploading it.

    python scripts/make_alt_jd.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _console  # noqa: F401  (configures stdout encoding on import)

from scripts.make_synthetic_corpus import render_pdf

JD = """DataForge Analytics
Backend & Data Engineering Intern

About the role
We are a small platform team building the pipelines and services behind our
analytics product. You will work alongside two senior engineers and own real
features from schema to deployment.

Required Skills
- Strong Python, including writing testable code
- SQL and relational database design, ideally PostgreSQL
- Building and consuming REST APIs
- Docker for local development and deployment
- Git and a working habit of code review
- Data structures and an understanding of algorithmic complexity

Preferred Skills
- Django or FastAPI experience is a strong plus
- Familiarity with pandas for data analysis
- Exposure to AWS or another cloud platform
- Celery or any task queue
- CI/CD pipelines

What you will do
- Design schemas and write the migrations behind them
- Build internal APIs the analytics dashboard consumes
- Containerise services and help move them to staging
- Write tests, review pull requests and keep the pipeline green

Location
Bengaluru, hybrid. Six month internship with a full-time conversion path.
"""

DEST = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "synthetic" / "jd_dataforge.pdf"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(JD, DEST)
    print(f"wrote {DEST.relative_to(DEST.parent.parent.parent)}")
    print("  a Python/data role, to contrast with the JavaScript full-stack jd_technova.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
