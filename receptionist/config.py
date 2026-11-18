"""Agent configuration: what the admin UI edits and what every call reads."""

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.default.json"  # committed defaults
LIVE_PATH = ROOT / "config.json"  # written by the admin UI, gitignored

# LiveKit Inference voices as "provider/model:voice". The string goes straight into the session's tts.
VOICES = {
    "cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc": "Jacqueline (Cartesia), confident American female",
    "cartesia/sonic-3:a167e0f3-df7e-4d52-a9c3-f949145efdab": "Blake (Cartesia), energetic American male",
    "deepgram/aura-2:athena": "Athena (Deepgram), smooth professional female",
    "deepgram/aura-2:odysseus": "Odysseus (Deepgram), calm professional male",
    "inworld/inworld-tts-2:Ashley": "Ashley (Inworld), warm American female",
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
