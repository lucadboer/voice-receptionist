import pytest

from receptionist.guardrails import is_emergency


@pytest.mark.parametrize(
    "text",
    [
        "I smell gas in my kitchen",
        "It smells like gas near the stove",
        "I think we have a gas leak",
        "There's a smell like rotten eggs in the basement",
        "Our carbon monoxide alarm keeps going off",
        "The CO detector is beeping",
        "There's smoke coming out of the furnace",
        "The outlet by the water heater is sparking",
        "There's a fire in the garage",
        "The dryer caught fire",
        "My water heater is on fire",
        "I can see flames behind the dryer",
    ],
)
def test_life_safety_phrases_match(text):
    assert is_emergency(text)


@pytest.mark.parametrize(
    "text",
    [
        "My gas furnace won't start",
        "The furnace won't fire up",
        "The burner won't fire at all",
        "My gas water heater is leaking",
        "The AC is blowing warm air",
        "Can I talk to a real person?",
        "How much does a furnace tune-up cost?",
        "My zip code is 78704",
    ],
)
def test_everyday_problems_do_not_match(text):
    assert not is_emergency(text)
