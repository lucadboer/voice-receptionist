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
from livekit.agents import AgentSession
from livekit.agents.llm import ChatContext
from livekit.plugins import anthropic

from agent import LLM_MODEL
from receptionist.agent import Receptionist
from receptionist.config import DEFAULT_PATH, load_config
from receptionist.tools import CallState

load_dotenv()

TODAY = date(2026, 11, 18)  # a Wednesday, so "tomorrow" is Thursday the 19th
JUDGE_MODEL = "claude-sonnet-5-5"  # a stronger model than the agent's, so the judge does not share its blind spots
CONFIG_PATH = Path(os.getenv("EVAL_CONFIG", DEFAULT_PATH))
MAX_WORDS = 50  # the booking read-back, the longest turn, is about 40 words


def pytest_addoption(parser):
    parser.addoption("--runs", type=int, default=1, help="run every eval this many times")


def pytest_generate_tests(metafunc):
    runs = metafunc.config.getoption("runs")
    if runs > 1:
        metafunc.fixturenames.append("run")
        metafunc.parametrize("run", range(1, runs + 1))


@pytest.fixture(autouse=True)
def api_key():
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("the evals call a real model: set ANTHROPIC_API_KEY")


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
    async with anthropic.LLM(model=LLM_MODEL) as model, AgentSession(llm=model, userdata=state) as session:

        async def start(call_config=config):
            await session.start(Receptionist(call_config, TODAY), capture_run=True)
            return session

        yield start
        lines_this_turn = 0
        for message in session.history.messages():
            if message.role == "user":
                lines_this_turn = 0
                continue
            assert_speakable(message.text_content or "")
            # One short line from a tool, then the answer. A third line means the model narrated the lookup too.
            lines_this_turn += 1
            assert lines_this_turn <= 2, f"three agent lines in one turn, ending with: {message.text_content!r}"


@pytest.fixture
async def judge():
    """Gives a function that asks a second model whether the last reply of a turn does what the intent says."""
    async with anthropic.LLM(model=JUDGE_MODEL) as model:

        async def check(result, intent):
            reply = result.expect[-1].is_message(role="assistant").event().item.text_content
            chat = ChatContext()
            chat.add_message(
                role="system",
                content="You grade one reply from a phone agent. Answer PASS or FAIL, then one sentence saying why.",
            )
            chat.add_message(role="user", content=f"The reply must do this: {intent}\n\nThe reply: {reply}")
            verdict = (await model.chat(chat_ctx=chat).collect()).text
            assert verdict.strip().upper().startswith("PASS"), f"{verdict}\nreply: {reply!r}"

        yield check
