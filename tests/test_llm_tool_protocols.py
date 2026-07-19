import asyncio

from agent.llm import ChatResponse, LLMClient, LLMProvider


def _response(provider: str) -> ChatResponse:
    if provider == "claude":
        raw = {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "call-1", "name": "demo",
                "input": {"query": "x"},
            }],
        }
    else:
        raw = {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "call-1", "type": "function",
                "function": {"name": "demo", "arguments": "{\"query\":\"x\"}"},
            }],
        }
        if provider == "deepseek":
            raw["reasoning_content"] = "temporary reasoning"
    return ChatResponse(
        tool_calls=[{"id": "call-1", "name": "demo", "arguments": {"query": "x"}}],
        raw_assistant_message=raw, provider=provider,
    )


def test_strict_schema_requires_nullable_optional_fields():
    prepared = LLMClient._prepare_tools([{
        "name": "demo", "description": "demo",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "required": True},
                "year": {"type": "integer"},
            },
            "required": ["query"],
        },
    }], strict=True)[0]
    schema = prepared["parameters"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"query", "year"}
    assert schema["properties"]["year"]["type"] == ["integer", "null"]
    assert "required" not in schema["properties"]["query"]


def test_deepseek_schema_is_injected_into_the_user_message_without_mutation():
    messages = [{"role": "user", "content": "生成最终回答"}]
    schema = {
        "type": "object",
        "properties": {
            "answer_markdown": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "followup_suggestions": {"type": "array"},
        },
        "required": ["answer_markdown", "evidence_refs", "followup_suggestions"],
        "additionalProperties": False,
    }
    enriched = LLMClient._with_deepseek_response_schema(messages, schema)
    assert messages == [{"role": "user", "content": "生成最终回答"}]
    content = enriched[-1]["content"]
    assert "DeepSeek JSON 输出契约" in content
    assert '"answer_markdown"' in content
    assert '"additionalProperties":false' in content
    assert "不要另建 answer、details" in content


def test_openai_tool_results_use_matching_role_tool_messages():
    async def scenario():
        client = object.__new__(LLMClient)
        client.provider = LLMProvider.OPENAI
        captured = {}

        async def chat(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return ChatResponse('{"answer_markdown":"ok","evidence_refs":[],"followup_suggestions":[]}')

        client.chat = chat
        await client.continue_with_tool_results(
            [{"role": "user", "content": "question"}], _response("openai"),
            [{"tool_call_id": "call-1", "payload": {"status": "completed"}}],
            [{"name": "demo", "description": "demo", "parameters": {
                "type": "object", "properties": {}, "required": [],
            }}], "answer", response_schema={"type": "object"},
        )
        messages = captured["messages"]
        assert [item["role"] for item in messages] == ["user", "assistant", "tool", "user"]
        assert messages[2]["tool_call_id"] == "call-1"
        assert captured["kwargs"]["tool_choice"] == "none"

    asyncio.run(scenario())


def test_claude_tool_results_share_one_adjacent_user_message_and_precede_text():
    async def scenario():
        client = object.__new__(LLMClient)
        client.provider = LLMProvider.CLAUDE
        captured = {}

        async def chat(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return ChatResponse("ok")

        client.chat = chat
        await client.continue_with_tool_results(
            [{"role": "user", "content": "question"}], _response("claude"),
            [
                {"tool_call_id": "call-1", "payload": {"status": "completed"}},
                {"tool_call_id": "call-2", "payload": {"status": "error"}, "is_error": True},
            ], [], "answer",
        )
        messages = captured["messages"]
        assert [item["role"] for item in messages] == ["user", "assistant", "user"]
        blocks = messages[-1]["content"]
        assert [block["type"] for block in blocks] == ["tool_result", "tool_result", "text"]
        assert blocks[1]["is_error"] is True
        assert captured["kwargs"]["tool_choice"] == "none"

    asyncio.run(scenario())


def test_deepseek_preserves_reasoning_content_during_tool_roundtrip():
    async def scenario():
        client = object.__new__(LLMClient)
        client.provider = LLMProvider.DEEPSEEK
        captured = {}

        async def chat(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return ChatResponse("ok")

        client.chat = chat
        await client.continue_with_tool_results(
            [{"role": "user", "content": "question"}], _response("deepseek"),
            [{"tool_call_id": "call-1", "payload": {"status": "completed"}}],
            [{"name": "demo", "description": "demo", "parameters": {
                "type": "object", "properties": {}, "required": [],
            }}], "answer", response_schema={"type": "object"},
        )
        assert captured["messages"][1]["reasoning_content"] == "temporary reasoning"
        assert captured["kwargs"]["json_mode"] is True
        assert "tools" not in captured["kwargs"]
        assert "tool_choice" not in captured["kwargs"]

    asyncio.run(scenario())


def test_deepseek_probe_omits_tool_choice_for_thinking_mode():
    async def scenario():
        client = object.__new__(LLMClient)
        client.provider = LLMProvider.DEEPSEEK
        client.model = "deepseek-v4-flash"
        calls = []

        async def chat(messages, **kwargs):
            calls.append({"messages": messages, "kwargs": kwargs})
            if kwargs.get("tools"):
                return ChatResponse(
                    tool_calls=[{
                        "id": "probe-call", "name": "patentagent_connection_echo",
                        "arguments": {"token": "PA_OK"},
                    }],
                    raw_assistant_message={
                        "role": "assistant", "content": None,
                        "reasoning_content": "probe reasoning",
                        "tool_calls": [{
                            "id": "probe-call", "type": "function",
                            "function": {
                                "name": "patentagent_connection_echo",
                                "arguments": '{"token":"PA_OK"}',
                            },
                        }],
                    },
                    provider="deepseek",
                )
            if kwargs.get("response_schema"):
                return ChatResponse('{"status":"PA_OK"}', provider="deepseek")
            return ChatResponse(
                "工具往返成功", finish_reason="stop", provider="deepseek",
            )

        client.chat = chat
        result = await client.probe()

        assert "tool_choice" not in calls[0]["kwargs"]
        assert "tools" not in calls[1]["kwargs"]
        assert "tool_choice" not in calls[1]["kwargs"]
        assert calls[1]["kwargs"]["json_mode"] is False
        assert calls[1]["messages"][1]["reasoning_content"] == "probe reasoning"
        assert calls[2]["kwargs"]["json_mode"] is True
        assert result["tool_roundtrip"] is True
        assert result["structured_output"] is True

    asyncio.run(scenario())


def test_current_default_models_are_not_retired_aliases():
    assert LLMClient.DEFAULT_MODELS[LLMProvider.CLAUDE] == "claude-sonnet-4-6"
    assert LLMClient.DEFAULT_MODELS[LLMProvider.OPENAI] == "gpt-4.1"
    assert LLMClient.DEFAULT_MODELS[LLMProvider.DEEPSEEK] == "deepseek-v4-flash"
