"""Shared setup for the evals: the real model, a fixed date, and a speech check on every agent reply.

Run with `uv run pytest evals`. `--runs 5` repeats every eval five times.
`EVAL_CONFIG=config.json` evaluates the config saved by the admin UI instead of the default.
"""

import os
import re
from datetime import date
from pathlib import Path

import pytest
from dotenv import load_dotenv
from livekit.agents import AgentSession, APIConnectOptions, SessionConnectOptions, inference

from agent import LLM_MODEL
from receptionist.agent import Receptionist
from receptionist.config import DEFAULT_PATH, load_config
from receptionist.tools import CallState

load_dotenv()

TODAY = date(2026, 11, 18)  # a Wednesday, so "tomorrow" is Thursday the 19th
# A judge from another model family does not share the agent's blind spots or favor its wording.
JUDGE_MODEL = "openai/gpt-5.4-mini"
CONFIG_PATH = Path(os.getenv("EVAL_CONFIG", DEFAULT_PATH))
MAX_WORDS = 50  # the booking read-back, the longest turn, is about 40 words
# The free plan allows 100 model requests a minute. Wait for the next minute instead of failing an eval on a 429.
RETRY_RATE_LIMITS = SessionConnectOptions(llm_conn_options=APIConnectOptions(max_retry=6, retry_interval=10))


def pytest_addoption(parser):
    parser.addoption("--runs", type=int, default=1, help="run every eval this many times")


def pytest_generate_tests(metafunc):
    runs = metafunc.config.getoption("runs")
    if runs > 1:
        metafunc.fixturenames.append("run")
        metafunc.parametrize("run", range(1, runs + 1))


@pytest.fixture(autouse=True)
def livekit_keys():
    if not (os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET")):
        pytest.skip("the evals call a real model on LiveKit Inference: set LIVEKIT_API_KEY and LIVEKIT_API_SECRET")


def assert_speakable(text):
    """A reply can be right and still sound wrong once a voice reads it out."""
    assert re.search(r"[.?!]\s*$", text), f"not a full sentence: {text!r}"
    assert not re.search(r"[*#_`•]|^\s*(-|\d+\.)\s", text, re.MULTILINE), f"markdown or a list: {text!r}"
    assert not re.search(r"\d{3,}", text), f"digits a voice may read as one big number: {text!r}"
    assert len(text.split()) <= MAX_WORDS, f"too long for one turn on the phone: {text!r}"


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


@pytest.fixture
def state(tmp_path):
    return CallState(today=TODAY, bookings_path=tmp_path / "bookings.json")


@pytest.fixture
async def start_call(config, state):
    """Gives a function that starts a call and returns the session. Pass a changed config to test a variant."""
    async with (
        inference.LLM(LLM_MODEL) as model,
        AgentSession(llm=model, userdata=state, conn_options=RETRY_RATE_LIMITS) as session,
    ):

        async def start(call_config=config):
            await session.start(Receptionist(call_config, TODAY), capture_run=True)
            return session

        yield start
        for message in session.history.messages():
            if message.role == "assistant":
                assert_speakable(message.text_content or "")


@pytest.fixture
async def judge():
    async with inference.LLM(JUDGE_MODEL) as model:
        yield model
