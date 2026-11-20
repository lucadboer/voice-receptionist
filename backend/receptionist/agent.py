"""The receptionist agent, built fresh for every call from the saved config."""

from array import array
from collections.abc import AsyncIterable
from datetime import date

from livekit import rtc
from livekit.agents import Agent, ModelSettings, llm

from receptionist.config import AgentConfig
from receptionist.guardrails import EMERGENCY_LINE, is_emergency
from receptionist.prompt import build_greeting, build_instructions
from receptionist.tools import all_tools

VOICE_LEVEL = 650  # a 16-bit sample this loud is the voice: 2% of full scale
PRE_ROLL = 0.1  # seconds kept before the voice, so a soft first consonant is not clipped


def voice_start(samples: array, sample_rate: int) -> int | None:
    """Where to start playing: a little before the first sample at voice level. None while it is all lead-in."""
    first = next((i for i, sample in enumerate(samples) if abs(sample) > VOICE_LEVEL), None)
    return None if first is None else max(0, first - int(PRE_ROLL * sample_rate))


class Receptionist(Agent):
    def __init__(self, config: AgentConfig, today: date) -> None:
        tools = all_tools()
        tools_off = [tool.id for tool in tools if tool.id not in config.enabled_tools]
        super().__init__(
            instructions=build_instructions(config, today, tools_off),
            tools=[tool for tool in tools if tool.id in config.enabled_tools],
        )
        self.greeting = build_greeting(config)

    async def on_enter(self) -> None:
        # A fixed greeting, not a model reply: it starts at once and always says the same thing.
        self.session.say(self.greeting)

    async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings):
        """Answer the first emergency of the call with a fixed line; send every other turn to the model."""
        last = chat_ctx.items[-1]
        if last.type == "message" and last.role == "user" and is_emergency(last.text_content or ""):
            self.session.userdata.emergency = True
            # Once per call: a caller who is already outside needs answers, not the same warning again.
            if not any(message.text_content == EMERGENCY_LINE for message in chat_ctx.messages()):
                return EMERGENCY_LINE
        return Agent.default.llm_node(self, chat_ctx, tools, model_settings)

    async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        """Drop what the voice puts before the first word: a faint tick, then up to 0.4 seconds of near silence."""
        lead_in: array | None = array("h")
        async for frame in Agent.default.tts_node(self, text, model_settings):
            if lead_in is not None:
                lead_in.extend(frame.data)
                start = voice_start(lead_in, frame.sample_rate)
                if start is None:
                    continue
                voice = lead_in[start:]
                frame = rtc.AudioFrame(voice.tobytes(), frame.sample_rate, 1, len(voice))
                lead_in = None
            yield frame
