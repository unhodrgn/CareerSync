"""Load and validate the criteria blocklist (data/blocklist.yaml).

The file is reviewed config, not user input: a malformed rule or regex fails at load time.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_REQUIRED = ("id", "category", "law_ref", "reason", "patterns")


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    law_ref: str
    reason: str
    patterns: tuple[re.Pattern, ...]
    allow: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class Blocklist:
    version: str
    rules: tuple[Rule, ...]


class BlocklistError(ValueError):
    pass


def _compile(rule_id: str, patterns: list[str]) -> tuple[re.Pattern, ...]:
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            raise BlocklistError(f"rule {rule_id}: bad regex {p!r}: {e}") from e
    return tuple(compiled)


def parse_blocklist(data: dict) -> Blocklist:
    if not isinstance(data, dict) or not data.get("version") or not isinstance(data.get("rules"), list):
        raise BlocklistError("blocklist needs a 'version' and a 'rules' list")
    rules, seen = [], set()
    for raw in data["rules"]:
        missing = [k for k in _REQUIRED if not raw.get(k)]
        if missing:
            raise BlocklistError(f"rule {raw.get('id', '?')}: missing {', '.join(missing)}")
        if raw["id"] in seen:
            raise BlocklistError(f"duplicate rule id {raw['id']}")
        seen.add(raw["id"])
        rules.append(
            Rule(
                id=raw["id"],
                category=raw["category"],
                law_ref=raw["law_ref"],
                reason=raw["reason"].strip(),
                patterns=_compile(raw["id"], raw["patterns"]),
                allow=_compile(raw["id"], raw.get("allow") or []),
            )
        )
    return Blocklist(version=str(data["version"]), rules=tuple(rules))


@lru_cache(maxsize=4)
def load_blocklist(path: str | Path) -> Blocklist:
    with open(path, encoding="utf-8") as f:
        return parse_blocklist(yaml.safe_load(f))
