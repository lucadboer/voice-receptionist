"""The receptionist agent, built fresh for every call from the saved config."""

from datetime import date

from livekit.agents import Agent, ModelSettings, llm

from receptionist.config import AgentConfig
from receptionist.guardrails import EMERGENCY_LINE, is_emergency
from receptionist.prompt import build_greeting, build_instructions
from receptionist.tools import all_tools


class Receptionist(Agent):
    def __init__(self, config: AgentConfig, today: date) -> None:
        super().__init__(
            instructions=build_instructions(config, today),
            tools=[tool for tool in all_tools() if tool.id in config.enabled_tools],
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
