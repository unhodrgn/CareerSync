"""The AI components the services use, behind one place so tests can replace them."""
from ai.embedding.model import Embedder, get_embedder
from ai.embedding.skills import SkillDictionary, load_dictionary
from ai.llm.client import LLMClient, get_llm_client
from app.core.config import settings


def skills() -> SkillDictionary:
    return load_dictionary(settings.SKILLS_PATH)


def embedder() -> Embedder:
    return get_embedder()


def llm() -> LLMClient | None:
    return get_llm_client()
