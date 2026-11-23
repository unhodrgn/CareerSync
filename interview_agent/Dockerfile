# Interview Agent image (M5 S5; docs/DECISIONS.md D56, D79, D80, D86). Build context is the repo root (docker-compose.yml):
# the agent imports ai/ in-process and reads data/ (the two blocklists). Not used by the default `docker compose up`: the
# service is in the `voice` profile.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app
WORKDIR /app
# The full lock, resolved on Windows (D79): pip still resolves, so Linux-only dependencies are added; `pip check` fails the build
# on a conflict. After the first good Linux build, replace the lock with one frozen from this image (interview_agent/README.md).
COPY interview_agent/requirements.lock.txt /app/interview_agent/requirements.lock.txt
RUN python -m pip install -r /app/interview_agent/requirements.lock.txt \
    && python -m pip check
# Local model files, at build time so the container needs no manual step. In livekit-agents 1.8.12 no installed plugin has anything to
# download (Silero VAD ships inside its wheel; the v1-mini turn-detector fallback is inside livekit-local-inference), so the first
# command is a no-op that stays correct if a plugin starts to download. The second loads both models: a missing file fails the build.
RUN python -m livekit.agents download-files \
    && python -c "from livekit.plugins import silero; from livekit.local_inference import EOT; silero.VAD.load(); EOT().close(); print('local models load')"
COPY ai /app/ai
COPY data /app/data
COPY interview_agent /app/interview_agent
# The worker's own health endpoint (livekit-agents serves it on 8081 in `start`): 503 while it is not registered with LiveKit.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/', timeout=3)"]
CMD ["python", "-m", "interview_agent.voice", "start"]
