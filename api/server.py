"""HTTP API for the admin UI. The agent reads the saved config at the start of every call."""

from fastapi import FastAPI, HTTPException

from receptionist.config import VOICES, AgentConfig, load_config, save_config
from receptionist.prompt import CALL_RULES
from receptionist.tools import all_tools

app = FastAPI(title="Receptionist config")


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


@app.get("/api/config")
def get_config() -> AgentConfig:
    return load_config()


@app.put("/api/config")
def put_config(config: AgentConfig) -> AgentConfig:
    known = {tool.id for tool in all_tools()}
    unknown = [name for name in config.enabled_tools if name not in known]
    if unknown:
        raise HTTPException(422, f"Unknown tools: {', '.join(unknown)}")
    save_config(config)
    return config


@app.get("/api/options")
def get_options() -> dict:
    # The UI builds its tool checkboxes from this list, so a tool added to all_tools() shows up with no UI change.
    return {
        "tools": [{"name": tool.id, "description": first_line(tool.info.description)} for tool in all_tools()],
        "voices": [{"id": voice_id, "label": label} for voice_id, label in VOICES.items()],
        "call_rules": CALL_RULES,
    }
