"""Task 5 (LLM part): does the configured Groq model work with the exact request shape the agent uses?

Makes one free model-list lookup and two tiny REAL calls (one per prompt of the interview) with a synthetic answer. It never
falls back to another model: if the configured model fails, it prints why and exits non-zero. Nothing is sent to Anthropic.

Run:  python verify_llm.py        (needs GROQ_API_KEY and AI_MODE=llm in interview_poc/.env; LLM_MODEL defaults to openai/gpt-oss-120b)
Compare another model:  set LLM_MODEL for one run (see README); the reasoning effort is only sent to gpt-oss models.
"""
from __future__ import annotations

import asyncio
import sys

import openai

import prompts
from config import ConfigError, load_env_file, load_settings
from groq_llm import GROQ_BASE_URL, LlmUnavailable, VoiceGroq, complete_text
from guards import screen_closing, screen_followup

SYNTHETIC_ANSWER_1 = "멱등성은 같은 요청을 여러 번 보내도 결과가 한 번 보낸 것과 같은 성질입니다. 결제 요청을 재시도해도 이중 결제가 생기지 않게 해 줘서 중요합니다."
SYNTHETIC_ANSWER_2 = "멱등 키를 요청 헤더에 넣고, 서버가 같은 키의 결과를 저장해 두었다가 그대로 돌려주는 방식으로 구현합니다."


async def main() -> int:
    load_env_file()
    try:
        settings = load_settings(role="llm")
    except ConfigError as e:
        print(f"[verify_llm] {e}", file=sys.stderr)
        return 2

    # A model-list lookup (no tokens): the id of a Groq model contains a slash, so the list is checked instead of /models/{id}.
    client = openai.AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)
    try:
        listing = await client.models.list()
        found = next((m for m in listing.data if m.id == settings.llm_model), None)
    except Exception as e:  # noqa: BLE001
        print(f"[verify_llm] model lookup failed: {type(e).__name__}. No other model is tried.", file=sys.stderr)
        return 1
    finally:
        await client.close()
    if found is None:
        print(f"[verify_llm] model not found on Groq: {settings.llm_model}. No other model is tried.", file=sys.stderr)
        return 1
    print(f"[verify_llm] model found: {found.id} (context_window={getattr(found, 'context_window', '?')}, active={getattr(found, 'active', '?')})")

    llm = VoiceGroq(model=settings.llm_model, api_key=settings.groq_api_key, reasoning_effort=settings.reasoning_effort)
    print(f"[verify_llm] model={settings.llm_model} reasoning_effort={settings.reasoning_effort or 'not sent'}")
    cases = (
        ("follow-up", prompts.FOLLOWUP_SYSTEM, prompts.followup_input(prompts.QUESTION, SYNTHETIC_ANSWER_1), screen_followup),
        (
            "closing",
            prompts.CLOSING_SYSTEM,
            prompts.closing_input(prompts.QUESTION, SYNTHETIC_ANSWER_1, prompts.FALLBACK_FOLLOWUP, SYNTHETIC_ANSWER_2),
            screen_closing,
        ),
    )
    failed = 0
    for name, system, user, screen in cases:
        try:
            result = await complete_text(llm, system=system, user=user)
        except LlmUnavailable as e:
            print(f"[verify_llm] {name}: FAILED {e}", file=sys.stderr)
            failed += 1
            continue
        ttft = "n/a" if result.ttft_s is None else f"{result.ttft_s:.2f}s"
        passed = screen(result.text) is not None
        print(f"[verify_llm] {name}: ttft={ttft} total={result.total_s:.2f}s output screen={'pass' if passed else 'FAIL (the PoC would speak its fixed fallback)'}")
        print(f"             {result.text}")
    await llm.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
