# Voice receptionist on LiveKit Agents

Riley answers the phone for a small heating and plumbing company when the office is busy, so no caller ends up in voicemail. She books a technician visit, hands the call to a person, and handles a gas leak safely. A one-page admin UI changes her instructions, name, greeting, voice and tools, and the next call uses the new settings.

**Demo (5 min):** LOOM_LINK

## Setup (under 5 minutes)

You need [uv](https://docs.astral.sh/uv/), Node 20.19 or newer, the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/#setup) (`brew install livekit-cli` on macOS), an Anthropic API key (the LLM) and a Deepgram API key (speech-to-text and the voice, free credit on signup).

```bash
cp .env.example .env    # paste the two keys
make setup              # install backend and frontend dependencies
make call               # talk to Riley with your microphone (headphones help)
```

In a second terminal:

```bash
make admin              # admin UI at http://localhost:5173
make test               # unit tests, no keys needed
make evals              # 20 evals against the real model, about two minutes
```

Everything runs on your machine, with no LiveKit server or account. When a call ends, press `q` to leave the console.

Things to try: book a visit (your zip code is 78704), interrupt her, say "I smell gas in my kitchen", ask for a real person. Then turn off `transfer_to_human` in the admin UI and ask again.

## What I like about LiveKit

I run LiveKit at work, self-hosted on Kubernetes, with phone calls coming in through SIP trunks.

- **The framework owns the hard real-time parts.** Turn detection, interruptions and the media transport are done. My time goes into the conversation.
- **A model is one line.** I swapped the speech-to-text model after measuring it, and nothing else in the code moved.
- **The same agent runs everywhere.** This one runs in a terminal with a laptop microphone. The same code would take a phone call through a SIP trunk.
- **It is open source and testable.** When the docs ran out, I read the source. `session.run()` lets a test check tool calls and their arguments against the real model.

## What I built and the decisions I made

```
caller ── speech-to-text ── turn detection ── emergency check ── LLM ⇄ tools ── voice
                                                   │
admin UI ── API ── config.json ── read at the start of every call
```

| Path | What it is |
|---|---|
| `backend/agent.py` | Entrypoint: reads the config and builds the session for each call |
| `backend/receptionist/` | The agent, its five tools, the call rules, the emergency check, the schedule and the config |
| `backend/api/` | Three endpoints for the admin UI |
| `backend/tests/`, `backend/evals/` | Unit tests without keys, and evals against the real model |
| `frontend/` | The admin UI: one React page |

**The use case.** A home services company loses money when a call goes to voicemail. The call needs a lookup, an action and a handoff, so the tools come naturally: `check_service_area`, `find_available_slots`, `book_appointment`, `transfer_to_human` and LiveKit's `end_call`. It also has a real safety case: a caller who smells gas should not be offered an appointment.

**Pipeline, not speech-to-speech.** Speech-to-speech gives the lowest latency for a simple chat. This call has several tools, strict rules and wording that must be exact. Separate steps give me a fixed greeting, a fixed safety line, a check that runs before the model, and evals that run in text.

**Models.** Claude Haiku 5.5 is the LLM. Deepgram does speech-to-text (Nova-3) and the voice (Aura-2). I started with Deepgram Flux for speech-to-text. It held each final transcript for over a second, because it runs its own end-of-turn check. Nova-3 sends it in about 0.4 seconds, so answers start about 0.8 seconds sooner.

**Sounding like a phone call.**

- The greeting is fixed text, so it starts at once.
- The call rules ask for one or two short sentences, one question at a time, and no digits or symbols.
- Tools answer in spoken form: "tomorrow at two thirty in the afternoon". The model does not convert times or numbers.
- A lookup or a booking says one short line from code ("Let me pull up the schedule.") while the model writes the answer.
- When the caller cuts in, Riley stops. The SDK would pause and resume instead, but the local console does not pause audio, so she kept talking over the caller. I found it by recording a call through a loopback audio device, and turned the pause off.
- The voice puts a faint tick and a short silence before each reply. The agent trims that lead-in, so the first word comes clean and a little sooner.
- The goodbye cannot be cut off. Callers say "thanks, bye" over it, and the call used to end in silence.
- After a long silence Riley asks "Are you still there?", then says goodbye and hangs up.

**Guardrails: code where it must not fail, prompt where judgment is needed.**

- **Emergency.** A gas smell, carbon monoxide, smoke, fire or sparks is matched in code, in `llm_node`, just before the model would be called. The model is not called. Riley says a fixed safety line, and booking is blocked for the rest of the call. I put the check in `llm_node` and not in `on_user_turn_completed`, because the test runner and typed input skip that hook.
- **Two-step booking.** The first call to `book_appointment` saves nothing and returns the details to read back. The booking is written only on a second call, with the same details, after the caller has spoken again.
- **Call rules the operator cannot remove.** The admin UI edits the instructions. The phone style and the safety rules are added by code and shown read-only in the UI.

**Config that applies to the next call.** The config is read at the start of every call, never at import time. The admin UI writes `backend/config.json`; the committed defaults are in `backend/config.default.json`.

**Easy to extend.** A new tool is one function with `@function_tool` and one line in `all_tools()`. The admin UI builds its checkboxes from the API, so the tool shows up there with no UI change.

## What I would improve with more time

- **Response time.** Answers start about a second and a half after the caller stops, and most of that is the LLM. I would try a faster model, or speech-to-speech, against the same evals.
- **A real phone line.** A SIP trunk and a real transfer where the agent briefs the person first. Today `transfer_to_human` says its line and ends the local call.
- **Patience with numbers.** People pause in the middle of a phone number. Today a turn that sounds unfinished gets a second and a half. A number should get more, without slowing down a yes or no.
- **Audio evals at scale.** Recorded calls with noise, accents and phone-line audio.

## Why evals

With a voice agent, the hard question is not "does it work today". It is "can I change the prompt, the model or a tool tomorrow without breaking calls". Evals answer that, so this is the bonus I wanted to go deep on.

**What is in the suite.**

- **Evals (`make evals`).** They drive the real agent against the real model and check tool calls, arguments and what was saved. A second, stronger model judges only what code cannot check.
- **A speech check on every reply.** No markdown, no digits, at most 50 words. A reply can be correct and still be unspeakable.
- **One simulated caller.** A second model plays a caller for a whole conversation, and the eval checks the booking at the end.
- **One spoken eval.** A voice says the caller's lines, the real speech-to-text transcribes them, and the agent gets that transcript.
- **Unit tests (`make test`).** The rules that live in code, with no keys and no model.

**What the evals found.** The first full run found four defects in my own agent, all fixed: a tool switched off in the admin UI was still attempted, "911" was written in digits, stray text came out after the goodbye, and the agent dropped its name when asked who it was.

**Why this is hard for voice.**

- **A text eval has to guess what speech-to-text will write.** I typed "oh" and commas between digit groups. The real speech-to-text wrote "zero" and no commas.
- **A reply can read fine and sound wrong.** "911" and a stray `}` look harmless in a transcript. A caller hears them.
- **One pass is not a result.** The same eval passed nine runs and then failed one in five. You need repeats and pass rates.
- **Timing is invisible in text.** Interruptions, the delay before an answer and a pause in the middle of a number do not exist in a text eval.
