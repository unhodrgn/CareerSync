# Privacy and legal

How CareerSync limits what personal data reaches the LLM, how consent works, and which hiring criteria it refuses. Decisions: [docs/DECISIONS.md](../DECISIONS.md); technical details: [PROJECT_DOCUMENTATION.md](../../PROJECT_DOCUMENTATION.md).

## What the LLM sees (masking, D39)

The uploaded PDF is turned into text and masked once, at upload; only the masked text is stored and used afterwards, for the LLM and for the evidence quotes recruiters see. The PDF itself is not stored.

Before any text reaches the LLM, the CV is masked: email, phone, URLs, 주민번호, birth date and address by pattern, and, on a best-effort basis, names: the seeker's own name (the account name and its spellings such as romanized or without diacritics, labeled name lines such as 성명/Name, and a name at the top of the CV) and names on labeled lines such as 추천인/담당자/Reference. Other people's names without such a label, school and company names, and a name mentioned only by its given name are not masked.

What can still reach the LLM, and is tracked: unlabeled names of other people and unusual spellings (PROJECT_DOCUMENTATION.md issue 33), lines such as gender, age or military service (Q24), and company-written text such as a recruiter's own contact details in a JD (issue 40). Name masking applies to CVs uploaded after D39; CVs stored before keep their masked text.

## Consent (D17)

- Registration needs consent to personal data processing and to AI analysis. AI consent is required to upload a CV and to apply.
- Job recommendation uses a CV for jobs the seeker did not apply to, so it needs consent to the current consent text (D16); a user who consented to an older text consents again on the consent screen.
- A seeker can withdraw AI consent at any time: every new AI use of their data stops (CV analysis, applying, recommendation, a company's 다시 분석), and they leave the talent pool. Stored CVs, evaluations and applications stay, and a run queued before the withdrawal finishes.
- Appearing in talent recommendation needs a separate opt-in. Companies see an anonymous profile only, and contact details only after the seeker accepts an offer (D3, D19, D20).

The AI never decides: it gives scores and evidence, and every status change (서류 검토, 면접 예정, 합격, 불합격 …) is a recruiter's click.

## Discriminatory criteria (guardrail)

A company's criteria are checked live while typing and again on save and publish. `data/blocklist.yaml` blocks 채용절차법 제4조의3 items (physical condition such as height, weight or appearance; origin region; marital status; wealth; family background) plus gender, age, religion, disability and health, and school prestige, each tagged with its law (남녀고용평등법, 고령자고용법, 고용정책기본법, 장애인차별금지법). A blocked criterion shows the law that forbids it and is logged. Criteria the AI suggests from a JD go through the same check and are left out if blocked (D24).

Interview practice questions also pass `data/interview_blocklist.yaml`, which is written for question-style phrasing (marriage, children, dating, religion, age, appearance, origin, family, politics, health) (D21).

## Laws

- 채용절차법 제4조의3 (disallowed criteria are blocked at input)
- 개인정보 보호법 제37조의2 (consent and explanation for automated processing)
- AI 기본법

The `law_ref` values in the blocklists are an unverified reading of the law; their legal validity is still to be checked (Q14, PROJECT_DOCUMENTATION.md issue 21).

The product does not collect sensitive group attributes as fields; free text in a CV can still contain them (Q24). A bias audit on synthetic labeled data is planned.
