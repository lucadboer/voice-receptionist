.PHONY: setup call admin test evals

setup:  ## install the backend and frontend dependencies
	cd backend && uv sync
	npm --prefix frontend install

call:  ## talk to the agent with your microphone and speakers
	cd backend && lk agent console

admin:  ## config API on :8000 and admin UI on http://localhost:5173
	@trap 'kill 0' EXIT; (cd backend && uv run uvicorn api.server:app --port 8000) & \
	until curl -sf http://127.0.0.1:8000/api/config > /dev/null; do sleep 0.2; done; \
	npm --prefix frontend run dev

test:  ## unit tests, no keys needed
	cd backend && uv run pytest -q

evals:  ## behavior evals against the real model, needs the API keys
	cd backend && uv run pytest evals -q
