"""The Interview Agent of the practice interview (M5; docs/DECISIONS.md D52, D56, D58, D80).

A separate runtime with its own virtual environment. It runs the engine of `ai/interview/` in-process, reaches the backend only through
the internal agent API over HTTP, never imports `app.*`, never touches the database, and calls a model only through the engine's
`prepare_turn` / `ask` / `parse_turn` flow (`turn_model.py`). Nothing here imports LiveKit at import time, so the backend suite can run
the runner against the real application without the agent's packages.
"""
