"""Agent configuration: what the admin UI edits and what every call reads."""

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.default.json"  # committed defaults
LIVE_PATH = ROOT / "config.json"  # written by the admin UI, gitignored

# Deepgram Aura-2 voices. The id goes straight into the session's tts.
VOICES = {
    "aura-2-athena-en": "Athena, calm and professional (female)",
    "aura-2-thalia-en": "Thalia, clear and energetic (female)",
    "aura-2-andromeda-en": "Andromeda, casual and expressive (female)",
    "aura-2-odysseus-en": "Odysseus, calm and professional (male)",
    "aura-2-apollo-en": "Apollo, confident and casual (male)",
}


class AgentConfig(BaseModel):
    agent_name: str = Field(min_length=1, max_length=40)
    greeting: str = Field(min_length=1, max_length=300)
    voice: str
    instructions: str = Field(min_length=1, max_length=8000)
    enabled_tools: list[str]

    @field_validator("voice")
    @classmethod
    def voice_is_known(cls, voice: str) -> str:
        if voice not in VOICES:
            raise ValueError(f"unknown voice: {voice}")
        return voice


def load_config(path: Path | None = None) -> AgentConfig:
    """Read the live config if the admin UI has saved one, otherwise the committed default."""
    if path is None:
        path = LIVE_PATH if LIVE_PATH.exists() else DEFAULT_PATH
    return AgentConfig.model_validate_json(path.read_text())


def save_config(config: AgentConfig) -> None:
    """Write through a temp file, so a call that starts mid-save never reads half a file."""
    tmp = LIVE_PATH.with_suffix(".json.tmp")
    tmp.write_text(config.model_dump_json(indent=2) + "\n")
    os.replace(tmp, LIVE_PATH)
