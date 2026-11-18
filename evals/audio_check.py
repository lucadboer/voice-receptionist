"""Speak a booking call into the agent and check what the speech-to-text heard.

The text evals hand the model clean text. This script runs the real audio path instead:
`lk agent debugger --audio` speaks each caller line with text to speech into the agent's
microphone input, so speech-to-text, turn detection and the agent's voice all run.
It stops after the read-back, before any yes, so no booking is saved.

Run it from the repo root with `uv run python evals/audio_check.py`. It uses Inference credits.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PORT = "8777"  # not the debugger's default port, so another session on the machine is left alone
LINES = [
    "Hi, my furnace won't turn on.",
    "My zip code is seven eight seven oh four.",
    "Tomorrow at two thirty works.",
    "My name is Dana Smith, and my number is five one two, five five five, oh one three two.",
]
EXPECTED = {"check_service_area": ("zip_code", "78704"), "book_appointment": ("phone", "5125550132")}


def debugger(command, *args):
    """Run one `lk agent debugger` command and return its JSON output."""
    done = subprocess.run(
        ["lk", "agent", "debugger", command, "--port", PORT, "--json", *args], cwd=ROOT, capture_output=True, text=True
    )
    if done.returncode != 0:
        sys.exit(f"lk agent debugger {command} failed:\n{done.stderr}")
    return json.loads(done.stdout)


def main():
    if shutil.which("lk") is None:
        sys.exit("This check needs the LiveKit CLI. Install it with `brew install livekit-cli`.")
    load_dotenv(ROOT / ".env")  # lk reads the LiveKit project from these variables

    reached = {}
    debugger("start", "--audio")
    try:
        for line in LINES:
            turn = debugger("say", line)
            print(f"said:  {line}\nheard: {turn['heard']}\n")
            for event in turn["events"]:
                if event["type"] == "tool_call" and event["name"] in EXPECTED:
                    argument = EXPECTED[event["name"]][0]
                    reached[event["name"]] = re.sub(r"\D", "", json.loads(event["arguments"])[argument])
    finally:
        debugger("stop")

    failed = False
    for tool, (argument, expected) in EXPECTED.items():
        got = reached.get(tool)
        print(f"{argument} at {tool}: {got} (expected {expected})")
        failed = failed or got != expected
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
