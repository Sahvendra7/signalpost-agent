"""V3 attribution decisions (design §B2). Pure functions, no I/O.

One module per question:
  * names.py    — how does a name or social handle relate to the legal name?
  * operator.py — who operates the verified website (the company itself, a manager, another company, a group/brand)?
  * social.py   — is this profile the company's own?
  * news.py     — is this item a dated article, and is it about this company?
  * jobs.py     — is this a single, current advertisement by this employer?
Extraction stays in site_facts.py; these modules only decide, and every decision carries a stable code and a
plain-English basis that the envelope and the viewer show.
"""
from .decision import Decision  # noqa: F401
