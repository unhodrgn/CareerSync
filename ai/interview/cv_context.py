"""The one door the CV passes through on its way into the interview (docs/DECISIONS.md D61, D62, D85).

The stored masked CV still carries age, gender and military-service text (Q24), so nothing in `ai/interview/` reads it
directly. `clean_cv` (in `ai/guardrails/cv_clean.py` since D85, which describes its steps; re-exported here) makes the
version the interview may use, and this module is the only one of the interview package that imports it. The planning
prompt (`make_bank`), the evidence lines, the warm-up and every quote are built from `CleanCv.text` only.
"""
from collections.abc import Sequence

from ai.career.interview import CriterionInfo, Question, make_questions
from ai.embedding.model import Embedder
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.cv_clean import CleanCv, clean_cv  # noqa: F401  (re-exported: ai.interview, plan.py, validate.py)
from ai.interview.boundary import GatedClient
from ai.interview.sensitive import for_model, for_model_block
from ai.llm.client import LLMClient


def make_bank(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    masked_cv: str,
    embedder: Embedder,
    blocklists: Sequence[Blocklist],
    llm: LLMClient | None,
) -> tuple[list[Question], str]:
    """The D21 question bank for a practice interview. The planning prompt carries the cleaned CV (not the stored text) and
    the job text and criteria with whatever touches age, gender or military service left out, and goes to the model through
    `boundary.GatedClient`, which cuts every line again. Every `cv_quote` is verified against the cleaned CV. Everything
    else is `ai.career.interview.make_questions`, unchanged (same blocklists, same fallback to the template)."""
    safe_criteria = [
        CriterionInfo(c.id, name, c.category, for_model(c.description))
        for c in criteria
        if (name := for_model(c.name))  # a criterion whose name is itself about these topics gets no question
    ]
    gated = GatedClient(llm, "plan") if llm is not None else None
    return make_questions(for_model(job_title), for_model_block(job_text), safe_criteria, clean_cv(masked_cv).text, embedder, blocklists, gated)
