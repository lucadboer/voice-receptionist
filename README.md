# Voice receptionist on LiveKit Agents

Riley answers the phone for a small heating and plumbing company when the office is busy, so no caller ends up in voicemail. She books a technician visit, hands the call to a person, and handles a gas leak safely. A one-page admin UI changes her instructions, name, greeting, voice and tools, and the next call uses the new settings.

**Demo (5 min):** LOOM_LINK

## Setup (under 5 minutes)

You need [uv](https://docs.astral.sh/uv/), Node 20 or newer, the LiveKit CLI (`brew install livekit-cli`) and a LiveKit Cloud project. The free plan is enough.

```bash
cp .env.example .env    # paste the project URL, API key and API secret
make setup              # Python and admin UI dependencies
make call               # talk to Riley with your microphone (headphones help)
```

In a second terminal:

```bash
make admin              # admin UI at http://localhost:5173
make test               # 60 unit tests, no keys needed, 3 seconds
make evals              # 19 evals against the real model, about a minute
make audio-check        # one booking call spoken through the real audio path
```

The three LiveKit values are the only keys. Speech-to-text, the LLM and the voice all run through LiveKit Inference. To use your own provider keys, replace the model strings in `agent.py` with plugin instances. It is one line each.

No `lk` CLI? `uv run python agent.py console` also works. It is the older Python CLI and prints a deprecation notice.

Things to try on a call:

- "My water heater is leaking." Then follow her questions. Your zip code is 78704.
- Interrupt her while she lists the times.
- "I smell gas in my kitchen."
- "Can I talk to a real person?"
- "How much is a furnace repair?"
- In the admin UI, change the name and the voice and turn off `transfer_to_human`. Call again and ask for a person.

When a call ends, press `q` to leave the console. Bookings are saved to `data/bookings.json`. Delete the file to free the slots again.

## What I like about LiveKit

I run LiveKit at work, self-hosted on Kubernetes, with phone calls coming in through SIP trunks. These are the things I keep liking, and they showed up again in this project.

- **The framework owns the hard real-time parts.** Turn detection, interruptions and the media transport are done. My time goes into the conversation.
- **A model is one line.** In this project I swapped the speech-to-text model after measuring it, and nothing else in the code moved.
- **The same agent runs everywhere.** This agent runs in a terminal with a laptop microphone. The same code would take a phone call through a SIP trunk.
- **It is open source.** When the docs run out, I read the source. That is how I found that the test runner skips one of the hooks, which changed where I put the safety guardrail.
- **It is testable.** `session.run()` lets a test assert on tool calls and their arguments. The CLI debugger can also speak a caller's lines into the agent, so the real speech-to-text is part of the test.

## What I built

```
caller ── speech-to-text ── turn detection ── emergency check ── LLM ⇄ tools ── voice
                                                   │
admin UI ── API ── config.json ── read at the start of every call
```

| Path | What it is |
|---|---|
| `agent.py` | Worker entrypoint: reads the config, builds the session, handles silence and hang-up |
| `receptionist/agent.py` | The agent: fixed greeting, emergency check before the model |
| `receptionist/tools.py` | The five tools and what one call remembers between them |
| `receptionist/prompt.py` | The call rules that are always added to the operator's instructions |
| `receptionist/guardrails.py` | The emergency patterns and the fixed safety line |
| `receptionist/schedule.py` | Service area, open slots, spoken times, bookings (JSON files in `data/`) |
| `receptionist/config.py` | Config schema, load and save |
| `api/server.py` | Three endpoints for the admin UI |
| `admin/` | One React page (Vite, TypeScript) |
| `tests/` | Unit tests, no keys |
| `evals/` | Behavior evals against the real model |

**The use case.** A home services company is the kind of small business that loses money when a call goes to voicemail. The call needs a lookup, an action and a handoff, which is three tools without inventing any. It also has a real safety edge: a caller who smells gas should not be offered an appointment.

**The tools.** `check_service_area`, `find_available_slots`, `book_appointment`, `transfer_to_human` and LiveKit's `end_call`.

## Decisions

### Pipeline, not speech-to-speech

For a short, simple conversation, a speech-to-speech model gives the lowest latency. This call has several tools, strict rules and wording that must be exact, so I used speech-to-text, an LLM and a voice as separate steps. The fixed greeting, the fixed safety line, the check that runs before the model, and evals that run in text all depend on that split. The voice platform I work on made the same move: its first version was speech-to-speech and today it is a pipeline.

### Models picked by measuring

I timed six LLMs through LiveKit Inference from my machine. Gemma 4 31B gave its first output in about 0.8 seconds. The other five took 1.0 to 2.5 seconds. All six made the right tool call, so the fastest one won.

The speech-to-text model mattered more. I started with Deepgram Flux. Scripted audio calls showed about 1.8 seconds between the caller's last word and Riley's first. The per-turn metrics showed where the time went. Flux has its own end-of-turn model and held the final transcript for about 1.2 seconds, and LiveKit's turn detector ran after that. Two end-of-turn checks in a row.

With Deepgram Nova-3 the transcript arrives about 0.4 seconds after the caller stops, and the response time dropped to about 1.0 second. Nova-3 has no end-of-turn model of its own, so I raised the minimum silence before a turn can end from 0.3 to 0.5 seconds. That leaves a caller room to pause in the middle of a phone number. It cost nothing I could measure, because the model is already writing its answer by then.

These numbers come from scripted calls with synthetic caller audio, run from my laptop. A real phone line adds its own delay.

### Sounding like a phone call

- **The greeting is fixed text, not a model reply.** It starts at once and never varies.
- **Short turns.** The call rules ask for one or two sentences and one question at a time, with no lists or symbols.
- **Tools answer in spoken form.** A slot comes back as "tomorrow at two thirty in the afternoon" and a phone number as "five one two, five five five, zero one three two". The model does not convert times or digits, so it cannot get them wrong.
- **A short line when a lookup starts.** A turn with a tool costs two model round trips. The tool says "Let me pull up the schedule." from code while the model writes the answer. There is at most one such line per caller turn. Two in a row sounded scripted.
- **Turn-taking is LiveKit's default.** The turn detector, interruptions and preemptive generation are on as shipped. I could not out-tune them in a day.
- **Silence.** After about fifteen quiet seconds Riley asks "Are you still there?". After ten more she says goodbye and hangs up.
- **The call ends.** Riley says goodbye and hangs up through `end_call`. A transfer and a silence timeout end the call the same way.

### Guardrails: code where it must not fail, prompt where judgment is needed

- **Emergency.** `guardrails.py` matches a gas smell, carbon monoxide, smoke, fire or sparks. The check runs in `llm_node`, just before the model would be called. On a match the model is not called at all. Riley says a fixed safety line, and booking is blocked for the rest of the call. The line is said once per call, because a caller who is already outside needs answers and not the same warning again.
- **Why `llm_node` and not `on_user_turn_completed`.** The hook looks like the natural place. But `session.run()`, console text mode and room text chat all skip it, so a guardrail there cannot be tested end to end and does not cover typed input. `llm_node` runs on every path.
- **Two-step booking.** The first call to `book_appointment` saves nothing and returns the details to read back. The booking is written only on a second call, with the same name, number and time, and only after the caller has spoken again. The model cannot say yes for the caller in the same turn, and what gets saved is what was read back.
- **Call rules the operator cannot remove.** The admin UI edits the instructions. The phone style and the safety rules are appended by code and shown read-only in the UI. An operator can change what Riley does, but not make her read markdown aloud or drop the emergency rule.
- **Prompt only.** No prices, no repair advice, staying in role and saying she is an AI when asked are prompt rules. The evals check them.
- **Two layers for emergencies.** The patterns are narrow on purpose, so "my gas furnace won't start" books a visit. An emergency in other words still reaches the model, and the call rules cover it. The evals test both layers.

### Config that applies to the next call

- **Read per call.** `load_config()` runs inside the entrypoint, never at import time. Workers keep warm processes, so a config read at import would be stale.
- **Two files.** `config.default.json` is committed. The admin UI writes `config.json`, which git ignores. Saving in the UI does not dirty the repo, and deleting `config.json` restores the defaults.
- **Atomic save.** The API writes a temp file and renames it, so a call that starts mid-save never reads half a file.
- **`{agent_name}`** in the greeting and the instructions is replaced with the name, so one field changes both.

### Easy to extend

Adding a tool is one function with `@function_tool` and one line in `all_tools()`. The admin UI builds its checkboxes from the API, so the new tool shows up there with no UI change, and the config decides which calls get it. A new voice is one line in `VOICES`.

### Left out on purpose

No database, no auth, no deployment and no UI styling beyond what makes the page readable. The brief asked for that. There is also no real phone number: `transfer_to_human` says its line and ends the local call, and a comment marks where the SIP transfer goes.

## What did not work at first

- **The emergency line looped.** A caller who said "we're outside, can someone look at the gas leak" got the evacuation line again. Now it is said once per call.
- **The transfer line got cut off.** The caller kept talking, the line was interrupted, and the call ended in silence. That line is now not interruptible.
- **The first speech-to-text model made every answer slow.** See "Models picked by measuring".
- **The model announced a transfer and then did not make it.** The tool description and one call rule now say the tool speaks its own handoff line.
- **The silence timer hung up on a caller who had answered.** In typed mode, a reply to "Are you still there?" did not stop the countdown, because a typed message does not change the user state. Now any caller message cancels it.
- **"For furnace won't turn on."** The read-back was built from the model's wording of the problem. The argument description now asks for a phrase that reads well after "for".

## What I would improve with more time

- **A real phone line.** A SIP trunk, the caller's number from the SIP headers instead of asking for it, and a real transfer: a cold one with SIP REFER, or a warm one where the agent briefs the person before connecting the caller.
- **Speech-to-speech as an option.** The same config and the same evals, run against a realtime model, to compare latency, task success and cost on this exact call.
- **A latency budget in CI.** I measured by hand. A scripted audio run that fails when the median response time goes over a limit would keep it honest.
- **Patience while the caller dictates a number.** People pause in the middle of a phone number. The agent should wait longer on that turn than on a yes or no.
- **Per-tenant config and tools.** The JSON file becomes a store keyed by tenant, and tools come from MCP servers so each tenant brings its own.
- **Audio evals at scale.** Recorded calls with noise, accents and phone-line audio, not only clean synthetic speech.

## Why evals

With a voice agent, the hard question is not "does it work today". It is "can I change the prompt, the model or a tool tomorrow without breaking calls". Evals are how I answer that at work, with golden datasets and an LLM judge, so this is the bonus I wanted to go deep on.

### What is in the suite

- **Unit tests (`make test`).** 60 tests with no keys and no model. They cover the rules that live in code: the emergency patterns, the two-step booking, config validation and the API.
- **Behavior evals (`make evals`).** 19 evals that drive the real agent against the real model, in text. Each one asserts on tool calls, their arguments and what was saved. An LLM judge from a different model family checks only what code cannot, like "does not tell the caller the visit is booked".
  - *Booking:* the full flow, no yes at the read-back, a changed time, a zip code outside the area, and numbers the way speech-to-text writes them ("seven eight seven oh four", "five twelve, five five five, oh one thirty two").
  - *Call rules:* a gas smell (the code layer), an emergency the patterns miss (the prompt layer), a transfer, a price question, a prompt injection, and "am I talking to a real person".
  - *Operator config:* a tool switched off in the admin UI, and a new agent name.
- **A speech check on every reply.** Every agent message in every eval must end like a sentence, have no markdown or lists, no run of digits a voice may read as one big number, and at most 50 words. A reply can be correct and still be unspeakable.
- **One simulated caller.** A second model plays a caller with a goal and gives each fact only when asked. The eval checks how the call ends: one booking, with the right name, number and an afternoon slot. The scripted evals check single decisions. This one checks a whole conversation.
- **Repeats.** `uv run pytest evals --runs 5` runs every eval five times, because model answers vary.
- **The live config.** `EVAL_CONFIG=config.json make evals` runs the suite against the config saved in the admin UI, so an operator can check a prompt edit before taking calls.
- **A spoken-audio check (`make audio-check`).** It speaks a booking call into the agent through the LiveKit CLI, so the real speech-to-text and turn detection run. It prints what was said next to what was heard, and fails if the zip code or phone number that reached the tools is wrong.

### What the evals found

The first full run found four defects in my own agent. All four are fixed in one commit, and the suite then passed 57 of 57 over three runs.

1. **A switched-off tool was still attempted.** With `transfer_to_human` off, the model called it anyway, got an error, and told the caller "Please hold for just a moment". On a phone that is a caller holding for no one. The prompt still mentioned the tool. Now the prompt names the tools that are off for the call.
2. **"Call 911" in digits.** The model copied the digits from its own prompt about half the time. Whether a voice reads those digits one by one is up to the TTS. The prompt now spells it out.
3. **Stray fragments after the goodbye.** After `end_call`, the model was asked for one more reply and sometimes produced `}` or half a word, which would go to the voice. `end_call` no longer asks for a second reply.
4. **The name got lost.** Asked "who am I speaking with?", the agent answered "I am an AI assistant" and dropped its name one time in five. The rule now separates the two questions.

### Why this is hard for voice

- **A text eval has to guess what speech-to-text will write.** I wrote "oh" and commas between digit groups. The real speech-to-text wrote "zero", no commas, and "ZIP" in capitals. I also changed the speech-to-text model during the day, which changed the agent's real input with no test noticing. Only the spoken check sees the real input.
- **A reply can read fine and sound wrong.** "911" and a stray `}` look harmless in a transcript. A caller hears them.
- **One pass is not a result.** An eval passed nine runs and then failed one in five. Two failures that looked like bad behavior were rate limits. You need repeats, pass rates, and a way to tell infrastructure errors from agent behavior.
- **The worst failures are promises.** "Please hold for a moment" reads as polite. The failure is in the tool layer, where the call never happened. The eval has to check the tool calls and judge the promise, because a caller on hold sees neither.
- **Timing is invisible in text.** Interruptions, the delay before an answer and a caller pausing in the middle of a number do not exist in a text eval. I measured those by hand in scripted audio calls.

The next steps would be recorded calls with noise and phone-line audio, and a latency budget that fails in CI.
