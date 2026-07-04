.PHONY: install playground run test clean

install:
	uv sync --link-mode=copy

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run python -m app.agent_runtime_app

test:
	uv run pytest

clean:
	rm -rf .venv .adk .pytest_cache .ruff_cache __pycache__ app/__pycache__
