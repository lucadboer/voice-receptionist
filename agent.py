"""Worker entrypoint. Run it with `lk agent console`, `lk agent dev` or `python agent.py console`."""

import asyncio

from dotenv import load_dotenv
from livekit.agents import (
    AgentServer,
    AgentSession,
    CloseEvent,
    ConversationItemAddedEvent,
    JobContext,
    UserStateChangedEvent,
    cli,
    inference,
)
from livekit.plugins import anthropic, deepgram

from receptionist.agent import Receptionist
from receptionist.config import load_config
from receptionist.tools import CallState

load_dotenv()

# Claude is the LLM. Deepgram does speech-to-text and the voice (the voice id comes from the config).
LLM_MODEL = "claude-haiku-5-5"
STT_MODEL = "nova-3"

STILL_THERE_LINE = "Are you still there?"
SILENCE_GOODBYE = "I'll let you go for now. Call us back anytime. Bye."
SECOND_SILENCE = 10  # seconds after "Are you still there?" before hanging up

server = AgentServer()


def hang_up_on_silence(session: AgentSession) -> None:
    """When the caller goes quiet, ask if they are still there, then say goodbye and end the call."""
    check_in: asyncio.Task | None = None

    async def check_in_then_hang_up() -> None:
        await session.say(STILL_THERE_LINE)
        await asyncio.sleep(SECOND_SILENCE)
        await session.say(SILENCE_GOODBYE)
        session.shutdown()

    def cancel_check_in() -> None:
        nonlocal check_in
        if check_in:
            check_in.cancel()
            check_in = None

    @session.on("user_state_changed")
    def on_user_state_changed(event: UserStateChangedEvent) -> None:
        nonlocal check_in
        cancel_check_in()
        if event.new_state == "away":
            check_in = asyncio.create_task(check_in_then_hang_up())

    @session.on("conversation_item_added")
    def on_message(event: ConversationItemAddedEvent) -> None:
        # A typed message does not change the user state, so a caller message also cancels the hang-up.
        if getattr(event.item, "role", None) == "user":
            cancel_check_in()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    config = load_config()  # read on every call, so a save in the admin UI applies to the next call
    state = CallState()
    session = AgentSession(
        stt=deepgram.STT(model=STT_MODEL),
        llm=anthropic.LLM(model=LLM_MODEL),
        tts=deepgram.TTS(model=config.voice),
        userdata=state,
        turn_handling={
            # LiveKit's turn detector, the version that runs on this machine and needs no cloud account.
            "turn_detection": inference.TurnDetector(version="v1-mini"),
            # Half a second of silence before a turn can end, so a caller can pause while dictating a number.
            "endpointing": {"min_delay": 0.5},
        },
    )
    hang_up_on_silence(session)

    async def delete_room() -> None:
        await ctx.delete_room()

    @session.on("close")
    def hang_up(_: CloseEvent) -> None:
        # However the session ends (goodbye, transfer or silence), deleting the room hangs up a phone caller.
        ctx.add_shutdown_callback(delete_room)
        ctx.shutdown()

    await session.start(agent=Receptionist(config, state.today), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
