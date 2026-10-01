"""Skill and certificate dictionary (data/skills.yaml): canonical names, aliases, lookup in text."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ai.guardrails.normalize import normalize

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "skills.yaml"


def _alias_pattern(alias: str) -> re.Pattern:
    # Word boundaries that also work next to Hangul and symbols such as "C++" or "Node.js"
    return re.compile(r"(?<![0-9a-z가-힣+#])" + re.escape(alias) + r"(?![0-9a-z+#])", re.IGNORECASE)


@dataclass(frozen=True)
class SkillDictionary:
    version: str
    # canonical name -> compiled alias patterns (canonical name included)
    skills: dict[str, tuple[re.Pattern, ...]]
    certificates: dict[str, tuple[re.Pattern, ...]]
    alias_to_skill: dict[str, str]

    def canonical(self, name: str) -> str | None:
        return self.alias_to_skill.get(normalize(name))

    def normalize_list(self, names: list[str]) -> list[str]:
        """Canonical names where known, original names otherwise; order kept, duplicates dropped."""
        out, seen = [], set()
        for raw in names:
            name = (raw or "").strip()
            if not name:
                continue
            canon = self.canonical(name) or name
            if canon.lower() not in seen:
                seen.add(canon.lower())
                out.append(canon)
        return out

    def find_in_text(self, text: str) -> list[str]:
        """Canonical skills mentioned in text, in order of first appearance."""
        hits = []
        low = normalize(text)
        for name, patterns in self.skills.items():
            pos = min((m.start() for p in patterns if (m := p.search(low))), default=None)
            if pos is not None:
                hits.append((pos, name))
        return [name for _, name in sorted(hits)]

    def find_certificates(self, text: str) -> list[tuple[str, str]]:
        """(canonical certificate, line it appears on) for each certificate mentioned in text."""
        out = []
        for line in text.splitlines():
            low = normalize(line)
            for name, patterns in self.certificates.items():
                if any(p.search(low) for p in patterns):
                    out.append((name, line))
        return out

    def lines_mentioning(self, skill: str, text: str) -> list[str]:
        patterns = self.skills.get(skill) or (_alias_pattern(normalize(skill)),)
        return [line.strip() for line in text.splitlines() if line.strip() and any(p.search(normalize(line)) for p in patterns)]


def parse_dictionary(data: dict) -> SkillDictionary:
    skills, certs, alias_to_skill = {}, {}, {}
    for name, aliases in (data.get("skills") or {}).items():
        names = {normalize(str(name)), *(normalize(str(a)) for a in aliases or [])}
        skills[name] = tuple(_alias_pattern(a) for a in sorted(names, key=len, reverse=True))
        for a in names:
            alias_to_skill[a] = name
    for name, aliases in (data.get("certificates") or {}).items():
        names = {normalize(str(name)), *(normalize(str(a)) for a in aliases or [])}
        certs[name] = tuple(_alias_pattern(a) for a in sorted(names, key=len, reverse=True))
    return SkillDictionary(version=str(data.get("version", "")), skills=skills, certificates=certs, alias_to_skill=alias_to_skill)


@lru_cache(maxsize=4)
def load_dictionary(path: Path = DEFAULT_PATH) -> SkillDictionary:
    return parse_dictionary(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
