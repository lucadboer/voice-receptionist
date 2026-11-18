.PHONY: setup call admin test evals audio-check

setup:  ## install the Python and admin UI dependencies
	uv sync
	npm --prefix admin install

call:  ## talk to the agent with your microphone and speakers
	lk agent console

admin:  ## config API on :8000 and admin UI on http://localhost:5173
	@trap 'kill 0' EXIT; uv run uvicorn api.server:app --port 8000 & \
	until curl -sf http://127.0.0.1:8000/api/config > /dev/null; do sleep 0.2; done; \
	npm --prefix admin run dev

test:  ## unit tests, no keys needed
	uv run pytest -q

evals:  ## behavior evals against the real model, needs the LiveKit keys
	uv run pytest evals -q

audio-check:  ## speak a booking call through the real audio path, uses Inference credits
	uv run python evals/audio_check.py
