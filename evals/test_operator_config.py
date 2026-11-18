"""Edits an operator makes in the admin UI reach the model on the next call."""


async def test_without_the_transfer_tool_the_agent_says_it_cannot_transfer(start_call, config, judge):
    config.enabled_tools = [tool for tool in config.enabled_tools if tool != "transfer_to_human"]
    session = await start_call(config)
    result = await session.run(user_input="Can I just talk to a real person, please?")

    # A call to a tool the agent was not given shows up only as an error output, not as a function call.
    tried = [event.item.name for event in result.events if event.type in ("function_call", "function_call_output")]
    assert "transfer_to_human" not in tried
    await result.expect[-1].is_message(role="assistant").judge(
        judge,
        intent="Says it cannot put the caller through to a person on this call. "
        "It does not claim to be connecting them and does not promise a callback.",
    )


async def test_a_new_agent_name_is_used_in_the_greeting_and_when_asked(start_call, config):
    old_name, config.agent_name = config.agent_name, "Marisol"
    session = await start_call(config)
    result = await session.run(user_input="Sorry, who am I speaking with?")

    greeting = session.history.messages()[0].text_content
    answer = result.expect[-1].is_message(role="assistant").event().item.text_content
    for text in (greeting, answer):
        assert "Marisol" in text and old_name not in text, text
