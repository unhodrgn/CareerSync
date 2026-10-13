"""The AI components the services use, behind one place so tests can replace them."""
from ai.embedding.model import Embedder, get_embedder
from ai.career.resources import Resources, load_resources
from ai.embedding.skills import SkillDictionary, load_dictionary
from ai.llm.client import LLMClient, ai_mode, get_llm_client
from app.core.config import settings


def skills() -> SkillDictionary:
    return load_dictionary(settings.SKILLS_PATH)


def resources() -> Resources:
    return load_resources(settings.LEARNING_RESOURCES_PATH)


def embedder() -> Embedder:
    return get_embedder()


def llm() -> LLMClient | None:
    return get_llm_client()


def mode() -> str:
    """`rules` or `llm` (AI_MODE)."""
    return ai_mode()
