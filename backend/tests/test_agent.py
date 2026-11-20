import json
import uuid
from array import array
from datetime import date

from livekit.agents import AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from receptionist.agent import Receptionist, voice_start
from receptionist.config import DEFAULT_PATH, load_config
from receptionist.guardrails import EMERGENCY_LINE
from receptionist.prompt import build_greeting
from receptionist.tools import CallState

TODAY = date(2026, 11, 18)
BOOKING = {
    "name": "Dana Smith",
    "phone": "5125550132",
    "slot_id": "2026-11-19T14:30",
    "issue": "a furnace that won't start",
}


class ScriptedLLM(llm.LLM):
    """Plays back a script: a string is a reply, a (tool name, arguments) pair is a tool call."""

    def __init__(self, *script):
        super().__init__()
        self.script = list(script)

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        if not self.script:
            raise AssertionError("the model was called with nothing left in the script")
        step = self.script.pop(0)
        return ScriptedStream(self, step, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class ScriptedStream(llm.LLMStream):
    def __init__(self, model, step, **kwargs):
        super().__init__(model, **kwargs)
        self.step = step

    async def _run(self):
        if isinstance(self.step, str):
            delta = llm.ChoiceDelta(role="assistant", content=self.step)
        else:
            name, arguments = self.step
            call = llm.FunctionToolCall(name=name, arguments=json.dumps(arguments), call_id=uuid.uuid4().hex)
            delta = llm.ChoiceDelta(role="assistant", tool_calls=[call])
        self._event_ch.send_nowait(llm.ChatChunk(id="scripted", delta=delta))


def default_config():
    return load_config(DEFAULT_PATH)


def tool_outputs(result):
    return [event.item.output for event in result.events if event.type == "function_call_output"]


def replies(result):
    return [event.item.text_content for event in result.events if event.type == "message"]


async def test_greeting_is_said_word_for_word(tmp_path):
    config = default_config()
    async with AgentSession(llm=ScriptedLLM(), userdata=CallState(TODAY, tmp_path / "bookings.json")) as session:
        result = await session.start(Receptionist(config, TODAY), capture_run=True)
    assert replies(result) == [build_greeting(config)]
    assert "Riley" in build_greeting(config)


async def test_emergency_is_answered_without_the_model_and_blocks_booking(tmp_path):
    state = CallState(TODAY, tmp_path / "bookings.json")
    model = ScriptedLLM()  # an empty script raises if the model is called
    async with AgentSession(llm=model, userdata=state) as session:
        await session.start(Receptionist(default_config(), TODAY))
        result = await session.run(user_input="I smell gas in my kitchen")
        assert replies(result) == [EMERGENCY_LINE]
        assert not any(event.type == "function_call" for event in result.events)
        assert state.emergency

        model.script += [("book_appointment", BOOKING | {"caller_confirmed": False}), "I can't book that right now."]
        result = await session.run(user_input="Can you still book me for tomorrow afternoon?")
        assert tool_outputs(result) == [str({"ok": False, "reason": "emergency"})]
    assert not state.bookings_path.exists()


async def test_the_emergency_line_is_said_once_per_call(tmp_path):
    model = ScriptedLLM("Glad you're safe. I'll connect you with our on-call team.")
    async with AgentSession(llm=model, userdata=CallState(TODAY, tmp_path / "bookings.json")) as session:
        await session.start(Receptionist(default_config(), TODAY))
        await session.run(user_input="I smell gas in my kitchen")
        result = await session.run(user_input="We're outside now. Can someone come look at the gas leak?")
    assert replies(result) == ["Glad you're safe. I'll connect you with our on-call team."]


async def test_the_model_cannot_confirm_for_the_caller(tmp_path):
    state = CallState(TODAY, tmp_path / "bookings.json", zip_code="78704")
    model = ScriptedLLM(
        ("book_appointment", BOOKING | {"caller_confirmed": False}),
        ("book_appointment", BOOKING | {"caller_confirmed": True}),
        "Does that sound right?",
        ("book_appointment", BOOKING | {"caller_confirmed": True}),
        "You're all set.",
    )
    async with AgentSession(llm=model, userdata=state) as session:
        await session.start(Receptionist(default_config(), TODAY))
        result = await session.run(user_input="Dana Smith, five one two, five five five, zero one three two")
        read_back, early_confirm = tool_outputs(result)
        assert "'status': 'needs_confirmation'" in read_back
        assert early_confirm == str({"ok": False, "reason": "read_back_required"})
        assert not state.bookings_path.exists()

        result = await session.run(user_input="Yes, that's right")
        assert tool_outputs(result) == [
            str({"ok": True, "status": "booked", "spoken": "tomorrow at two thirty in the afternoon"})
        ]
    assert len(json.loads(state.bookings_path.read_text())) == 1


def test_a_disabled_tool_is_not_given_to_the_agent():
    config = default_config()
    config.enabled_tools.remove("book_appointment")
    agent = Receptionist(config, TODAY)
    assert {tool.id for tool in agent.tools} == {
        "check_service_area",
        "find_available_slots",
        "transfer_to_human",
        "end_call",
    }


def test_voice_start_skips_the_tick_and_keeps_a_pre_roll():
    rate = 24000
    tick, silence, voice = [200] * 240, [0] * 7200, [9000] * 100  # 10 ms tick, 300 ms of nothing, then the voice
    samples = array("h", tick + silence + voice)
    assert voice_start(samples, rate) == 240 + 7200 - 2400  # 100 ms before the voice


def test_voice_start_waits_while_there_is_only_lead_in():
    assert voice_start(array("h", [200] * 240 + [0] * 1000), 24000) is None
