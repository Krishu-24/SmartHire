"""
Generate `fixtures/jds/` — three job descriptions with genuinely different shapes.

Written to match how real postings in each segment are actually worded, because
the engine's JD reader is only as good as the prose it has seen: requirement
blocks, inline hedges ("a strong plus"), responsibilities mixed with skills, and
the coded language a bias audit is supposed to catch.

The companies are FICTIONAL. Putting a real employer's name on a job description
we wrote would misrepresent them, and none of the engine's behaviour depends on
the name — only on the requirements underneath it.

    sde_intern    Software Development Intern, consumer fintech  (JS full-stack)
    backend_job   Software Engineer, Backend — full-time, 2+ yrs (Python/infra)
    data_intern   Data Science Intern, B2B SaaS                  (Python/ML)

`sde_intern` deliberately contains the phrases the JD audit exists to find —
"rockstar", "young and energetic", a tier-1 college filter and a years-of-
experience bar on an internship — so the bias panel has something real to report
on the sample a judge is most likely to open first.

    python scripts/make_sample_jds.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _console  # noqa: F401  (configures stdout encoding on import)

from scripts.make_synthetic_corpus import render_pdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / "fixtures" / "jds"


SDE_INTERN = """PaySprint Technologies
Software Development Intern (6 months, Bangalore)

About us
PaySprint builds the payments layer behind a few hundred Indian D2C brands. We
are forty people, eleven of them engineers, and interns here own features rather
than tickets.

Who we are looking for
We want a young and energetic coding rockstar to join our fast-paced team. You
should be a self-starter who thrives under pressure and can hit the ground
running from day one.

Required Skills
- Strong JavaScript fundamentals, including ES6+ and async patterns
- React for building component-driven interfaces
- Node.js and Express for writing REST APIs
- MongoDB or any document database, including schema design
- Git, and a working habit of opening pull requests
- HTML and CSS, with responsive layouts that hold up on mobile
- 2+ years experience building production web applications

Preferred Skills
- TypeScript is a strong plus
- Familiarity with Docker for local development
- Exposure to AWS, particularly S3 and EC2
- Jest or any testing framework
- Experience with CI/CD pipelines is desirable

What you will do
- Build customer-facing screens in React alongside two senior engineers
- Write and document the Node.js endpoints those screens consume
- Model MongoDB collections for new payment flows
- Take part in code review, both giving and receiving
- Help containerise services as we move staging to Docker

Eligibility
- B.Tech/B.E. in Computer Science from a tier-1 college preferred
- Graduating in 2026 or 2027
- Available for a full-time 6-month internship in our Bangalore office

Compensation
INR 40,000 per month, with a pre-placement offer for strong performers.
"""


BACKEND_JOB = """Northwind Logistics Cloud
Software Engineer, Backend (Full-time, Pune / Hybrid)

The role
Northwind runs the routing and fleet telemetry platform used by mid-size Indian
logistics operators. You will join the Platform team, which owns the services
that ingest around 40 million GPS events a day and the APIs that sit on top of
them. This is a hands-on engineering role with real production ownership.

Required Skills
- Strong Python, with demonstrated experience writing testable, maintainable code
- Solid understanding of relational database design; PostgreSQL in production
- Designing and building REST APIs that other teams depend on
- Docker, and comfort debugging a container that will not start
- Git and code review as a daily habit
- Data structures and algorithmic complexity, applied to real throughput problems
- Linux fundamentals: processes, networking, log spelunking
- 2-4 years of professional backend engineering experience

Preferred Skills
- Django or FastAPI in a production setting is a strong plus
- Celery or another task queue for asynchronous work
- Redis for caching and rate limiting
- Exposure to AWS, particularly ECS, RDS and S3
- Kubernetes experience is nice to have, not required
- Familiarity with monitoring and alerting; Prometheus or similar
- CI/CD pipeline design

Responsibilities
- Own services end to end, from schema design through to production alerts
- Build and version the internal APIs the dispatch dashboard consumes
- Profile and fix throughput bottlenecks in the ingestion path
- Write migrations that run safely against a live database
- Take part in an on-call rotation, roughly one week in six
- Mentor interns and review their pull requests

What we offer
Competitive salary, hybrid working (two days in the Pune office), and a genuine
engineering culture where design documents are read and argued with.
"""


DATA_INTERN = """Cohere Retail Analytics
Data Science Intern (Summer, Remote within India)

About the team
Cohere Retail Analytics builds demand forecasting for grocery chains. The data
team is six people. Interns work on a real model that a real merchandiser
depends on, not a sandbox.

What you will need
- Strong Python, particularly for data manipulation
- pandas for cleaning and reshaping messy real-world data
- SQL, including joins and window functions against a warehouse
- Machine learning fundamentals: train/test discipline, overfitting, evaluation
- An ability to explain a model's limitations as clearly as its accuracy
- Git for version control

Nice to have
- scikit-learn for classical modelling is a strong plus
- Exposure to deep learning frameworks such as PyTorch or TensorFlow
- Familiarity with data visualisation and communicating results
- Experience with Docker for reproducible environments
- Any exposure to cloud platforms, GCP preferred
- Statistics coursework beyond an introductory level

Your project
- Clean and join three years of point-of-sale data across 400 stores
- Build a baseline forecast and beat it, documenting both
- Evaluate honestly: report where the model fails, not just where it works
- Write up the analysis so a non-technical merchandiser can act on it
- Ship the final model behind a small internal API

Eligibility
- Currently pursuing a degree in any quantitative discipline
- Available full-time for 10-12 weeks over the summer
- Comfortable working remotely with a distributed team

Stipend
INR 35,000 per month.
"""


JDS = {
    "jd_paysprint_sde_intern": SDE_INTERN,
    "jd_northwind_backend_job": BACKEND_JOB,
    "jd_cohere_data_intern": DATA_INTERN,
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)

    for name, text in JDS.items():
        pdf = DEST / f"{name}.pdf"
        txt = DEST / f"{name}.txt"
        render_pdf(text, pdf)
        txt.write_text(text, encoding="utf-8")
        title = text.strip().splitlines()[1]
        print(f"  wrote {pdf.relative_to(ROOT)}")
        print(f"        {title}")

    print(f"\n{len(JDS)} sample job descriptions in {DEST.relative_to(ROOT)}")
    print("Upload any of them through the UI, or use Change JD to re-target a pool.")
    print("Company names are fictional; the requirements are shaped like real postings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
