"""Official learning resources from data/learning_resources.yaml; the only source of URLs in a roadmap."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learning_resources.yaml"


@dataclass(frozen=True)
class Resource:
    title: str
    url: str


@dataclass(frozen=True)
class Resources:
    version: str
    skills: dict[str, Resource]
    certificates: dict[str, Resource]

    def for_gap(self, name: str, kind: str) -> list[Resource]:
        found = (self.skills if kind == "skill" else self.certificates).get(name)
        return [found] if found else []


def _entries(data: dict) -> dict[str, Resource]:
    # Entries marked `verified: false` are kept in the file for review but never shown
    return {name: Resource(e["title"], e["url"]) for name, e in (data or {}).items() if e.get("verified", True)}


@lru_cache(maxsize=4)
def load_resources(path: Path = DEFAULT_PATH) -> Resources:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Resources(str(data.get("version", "")), _entries(data.get("skills")), _entries(data.get("certificates")))
