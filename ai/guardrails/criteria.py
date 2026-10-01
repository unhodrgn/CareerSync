"""Criteria guardrail: block evaluation criteria that the law disallows (채용절차법 제4조의3 and related laws).

Deterministic and rule-based: the same input always gives the same answer, and every block names
the rule, the matched text and the law. Called through `check_criterion` only.
"""
from dataclasses import dataclass, field

from ai.guardrails.blocklist import Blocklist, Rule
from ai.guardrails.normalize import normalize


@dataclass(frozen=True)
class GuardrailHit:
    field: str  # "name" | "description"
    rule_id: str
    category: str
    matched: str
    reason: str
    law_ref: str


@dataclass(frozen=True)
class GuardrailResult:
    blocklist_version: str
    hits: tuple[GuardrailHit, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return not self.hits


def _rule_hit(rule: Rule, text: str) -> str | None:
    """First matched text for this rule that no allow pattern covers, or None."""
    allowed_spans = [m.span() for a in rule.allow for m in a.finditer(text)]
    for pattern in rule.patterns:
        for m in pattern.finditer(text):
            start, end = m.span()
            if not any(a_start <= start and end <= a_end for a_start, a_end in allowed_spans):
                return m.group(0)
    return None


def check_criterion(name: str, description: str, blocklist: Blocklist) -> GuardrailResult:
    hits = []
    for field_name, raw in (("name", name), ("description", description or "")):
        text = normalize(raw)
        if not text:
            continue
        for rule in blocklist.rules:
            if (matched := _rule_hit(rule, text)) is not None:
                hits.append(
                    GuardrailHit(
                        field=field_name,
                        rule_id=rule.id,
                        category=rule.category,
                        matched=matched,
                        reason=rule.reason,
                        law_ref=rule.law_ref,
                    )
                )
    return GuardrailResult(blocklist_version=blocklist.version, hits=tuple(hits))
