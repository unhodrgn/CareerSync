"""Facts the docs copy from the repo: the demo accounts and password (scripts/seed.py, read without importing it,
since importing sets AI_MODE and builds a database engine) and the migration range (the revision chain in
backend/migrations/versions). Hand-typed test counts are kept out of the docs instead of being guarded."""
import ast
import re
from pathlib import Path

from .markdown import ROOT, Doc, guarded_docs, place, report

SEED = "scripts/seed.py"
VERSIONS = "backend/migrations/versions"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.test\b")
PASSWORD = re.compile(r"\bdemo\d+\b")
RANGE = re.compile(r"`?\b(\d{4})`?\s*(?:…|\.\.\.|→|->)\s*`?(\d{4})\b`?")
MIGRATION_ID = re.compile(r"\bmigrations?\s+`?(\d{4})\b`?", re.IGNORECASE)
# Every pytest summary names passed or skipped; a bare "failed" is too common ("port 5432 failed")
TEST_COUNT = re.compile(r"\b\d+\s+(?:passed|skipped|deselected|tests?)\b", re.IGNORECASE)


def seed_accounts(source: str) -> tuple[dict[str, int], str | None]:
    """(email → line, password) from the seed's string constants."""
    tree = ast.parse(source)
    emails = {
        node.value: node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and EMAIL.fullmatch(node.value)
    }
    password = next(
        (
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PASSWORD" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ),
        None,
    )
    return emails, password


def account_problems(docs: list[Doc], emails: dict[str, int], password: str | None) -> list[str]:
    problems, named = [], set()
    for doc in docs:
        for line, text in doc.numbered():  # the seed output block counts too
            for email in EMAIL.findall(text):
                named.add(email)
                if email not in emails:
                    problems.append(f"{doc.rel}:{line} names the demo account {email}, which {SEED} does not create. Fix the doc or the seed.")
            for word in PASSWORD.findall(text):
                if word != password:
                    problems.append(f"{doc.rel}:{line} gives the demo password {word}; {place(SEED, r'^PASSWORD')} sets {password!r}. Fix the doc or the seed.")
    for email, line in sorted(emails.items()):
        if email not in named:
            problems.append(f"{SEED}:{line} creates {email}, which no doc lists. Add it to the demo accounts in the README, or drop it from the seed.")
    return problems


def revision_chain(versions: Path) -> tuple[list[str], list[str]]:
    """(revisions from first to head, problems with the chain)."""
    down, problems = {}, []
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision\s*=\s*"([^"]+)"', text, re.MULTILINE)
        prev = re.search(r'^down_revision\s*=\s*(?:"([^"]+)"|None)', text, re.MULTILINE)
        if rev and prev:
            down[rev.group(1)] = prev.group(1)
    chain = [r for r, d in down.items() if d is None]
    if len(chain) != 1:
        return [], [f"{VERSIONS}: expected one first migration, found {chain}"]
    while nxt := [r for r, d in down.items() if d == chain[-1]]:
        if len(nxt) > 1:
            problems.append(f"{VERSIONS}: {chain[-1]} has several next migrations {nxt} (branch)")
            break
        chain.append(nxt[0])
    return chain, problems


def migration_problems(docs: list[Doc], chain: list[str]) -> list[str]:
    problems, ranges = [], 0
    if not chain:
        return [f"{VERSIONS}: no migrations found"]
    first, head = chain[0], chain[-1]
    for doc in docs:
        for line, text in doc.numbered():  # trees in code blocks quote the range too
            # Only on a line about migrations: "0.0.0.0:5433->5432" is a port mapping
            for m in RANGE.finditer(text) if "migration" in text.lower() else ():
                ranges += 1
                if (m.group(1), m.group(2)) != (first, head):
                    problems.append(f"{doc.rel}:{line} gives the migrations as {m.group(1)} … {m.group(2)}; {VERSIONS} runs {first} … {head}. Fix the doc.")
            for m in MIGRATION_ID.finditer(text):
                if m.group(1) not in chain:
                    problems.append(f"{doc.rel}:{line} mentions migration {m.group(1)}, which {VERSIONS} does not have. Fix the doc.")
    if not ranges:
        problems.append(f"No doc gives the migration range ({first} … {head}) any more. Restore it (e.g. the README tree) or drop this check.")
    return problems


def count_problems(docs: list[Doc]) -> list[str]:
    """Hand-typed test counts go stale with every new test and differ per machine (e5 cached or not)."""
    return [
        f"{doc.rel}:{line} gives a test count ({m.group(0)!r}). Counts go stale: describe what must pass instead, "
        f"and use `pytest --collect-only -q | tail -1` to count."
        for doc in docs
        for line, text in doc.numbered()  # code blocks too
        for m in TEST_COUNT.finditer(text)
    ]


def test_no_hand_typed_test_counts():
    problems = count_problems(guarded_docs())
    assert not problems, report(problems)


def test_demo_accounts_match_the_seed():
    emails, password = seed_accounts((ROOT / SEED).read_text(encoding="utf-8"))
    problems = account_problems(guarded_docs(), emails, password)
    assert not problems, report(problems)


def test_migration_range_matches_the_revision_chain():
    chain, problems = revision_chain(ROOT / VERSIONS)
    problems += migration_problems(guarded_docs(), chain)
    assert not problems, report(problems)
