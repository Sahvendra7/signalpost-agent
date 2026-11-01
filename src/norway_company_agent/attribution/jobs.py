"""Is a job candidate a single, current advertisement by this employer (design §B7)?

Currency is decided from dates the advertisement states, never assumed:
  open             a stated application deadline or schema.org validThrough on or after the run date
  recently_posted  no closing date stated, posted at most 45 days before the run date (published with that basis,
                   never called "current")
  expired          the deadline has passed, or posted more than 45 days ago with no closing date
  undated          no date at all: currency unknown, not published
The employer is the one the advertisement names (hiringOrganization, or an "Arbeidsgiver:" label). With no employer
named, the company is presumed only on its own careers page and only when it is not a recruiter or staffing company,
whose job boards list their clients' vacancies.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .decision import Decision
from .names import LegalName, compact, fold

RECENT_DAYS = 45
RECRUITER_NACE = ("78.1", "78.2", "78.3")
GENERIC_TITLE = re.compile(r"\b(?:talentbank|talent pool|åpen søknad|apen soknad|open application|generell søknad|spontansøknad|registrer cv|send cv|"
                           r"bli med på laget|bli en av oss|vi søker alltid|vi soker alltid)\b", re.I)
VAGUE_SEASONAL = re.compile(r"^(?:lærling|laerling|lærlingeplass|sommerjobb|sommervikar|summer job|internship|trainee)s?$", re.I)


def _day(value: Any) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def is_recruiter(profile: dict[str, Any]) -> bool:
    live = ((profile.get("evidence") or {}).get("registry_live") or {}).get("value") or {}
    code = str((live.get("industry") or {}).get("kode") or "")
    return code.startswith(RECRUITER_NACE)


def currency(job: dict[str, Any], run_date: date) -> tuple[str, str]:
    deadline = _day(job.get("application_deadline")) or _day(job.get("valid_through"))
    if deadline is not None:
        if deadline >= run_date:
            return "open", f"application deadline {deadline.isoformat()} (open on {run_date.isoformat()})"
        return "expired", f"application deadline {deadline.isoformat()} has passed"
    posted = _day(job.get("date_posted"))
    if posted is not None:
        age = (run_date - posted).days
        if 0 <= age <= RECENT_DAYS:
            return "recently_posted", f"posted {posted.isoformat()}, {age} days before retrieval; no closing date stated"
        return "expired", f"posted {posted.isoformat()}, {age} days before retrieval, with no closing date"
    return "undated", "no posting date or deadline stated; whether the position is still open is unknown"


def employer(job: dict[str, Any], legal: LegalName, operator_kind: str, recruiter: bool) -> Decision:
    named = str(job.get("hiring_organization") or job.get("employer_label") or "").strip()
    if named:
        value = compact(named)
        if legal.phrase_in(named) or (legal.compact and value.startswith(legal.compact) and not legal.strip_neutral(value[len(legal.compact):])):
            return Decision(True, "employer_named_is_company", f"The advertisement names the company as employer (\"{named}\").")
        return Decision(False, "other_employer", f"The advertisement names another employer (\"{named}\").")
    if recruiter:
        return Decision(False, "employer_unstated_on_job_board", "A recruitment company's job board lists its clients' vacancies; this one names no employer.")
    if operator_kind in ("self", "section", "platform"):
        return Decision(True, "employer_presumed_own_careers_page", "Listed on the company's own careers page; no other employer named.")
    return Decision(False, "employer_unstated_on_shared_site", "The website is shared with other companies, and the advertisement names no employer.")


def decide_job(job: dict[str, Any], *, legal: LegalName, operator_kind: str, recruiter: bool, run_date: date, on_news_page: bool) -> Decision:
    title = " ".join(str(job.get("title") or "").split())
    if job.get("method") == "jsonld_JobPosting" and on_news_page:
        return Decision(False, "job_on_news_page", "The advertisement sits in a news archive, where old advertisements stay listed.")
    if GENERIC_TITLE.search(fold(title)) or GENERIC_TITLE.search(title) or VAGUE_SEASONAL.match(fold(title).strip()):
        return Decision(False, "generic_recruitment", "A general recruitment page or open application, not an advertisement for one position.")
    owner = employer(job, legal, operator_kind, recruiter)
    if not owner.accepted:
        return owner
    state, basis = currency(job, run_date)
    if state not in ("open", "recently_posted"):
        return Decision(False, "currency_unknown" if state == "undated" else "expired", basis[:1].upper() + basis[1:] + ".")
    return Decision(True, state, f"{owner.basis} {basis[:1].upper() + basis[1:]}.")
