"""Emergency check that runs on every caller turn before the model is called.

It is plain code and not a prompt rule, so it gives the same answer every time
and the model cannot be talked out of it.
"""

import re

EMERGENCY_LINE = (
    "This could be dangerous. Please get everyone out of the house now and call nine one one from outside. "
    "Once you're safe, I can connect you with our on-call team."
)

# Life-safety cases only. Anything else goes to the model as a normal turn.
EMERGENCY_PATTERNS = [
    r"smell(s|ing)?( like| of)? gas|gas (smell|leak)|leak(s|ing)? gas|rotten eggs?",
    r"carbon monoxide|\bc\.? ?o\.? (alarm|detector)",
    r"\bsmok(e|ing)\b",
    r"\bspark(s|ing|ed)?\b",
    r"\b(a|on|caught) fire\b|\bflames?\b",  # not "won't fire": that is a furnace that will not start
]


def is_emergency(text: str) -> bool:
    """True when the caller describes a gas leak, carbon monoxide, smoke, fire or sparks."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in EMERGENCY_PATTERNS)
