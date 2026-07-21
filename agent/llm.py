"""多供应商 LLM 客户端封装"""

import json
import os
import asyncio
import time
import re
from copy import deepcopy
from enum import Enum
from typing import AsyncIterator, Optional


class LLMProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


class ChatResponse:
    """LLM 响应"""
    def __init__(self, text: str = "", tool_calls: list[dict] = None,
                 finish_reason: str = "", usage: dict | None = None,
                 request_id: str = "", provider: str = "", model: str = "",
                 raw_assistant_message: dict | None = None,
                 reasoning_content: str = ""):
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason or ""
        self.stop_reason = self.finish_reason
        self.usage = usage or {}
        self.request_id = request_id
        self.provider = provider
        self.model = model
        self.raw_assistant_message = raw_assistant_message or {}
        self.reasoning_content = reasoning_content or ""


class ChatEvent:
    """流式事件"""
    def __init__(self, event_type: str, content: str):
        self.type = event_type  # 'text_delta' | 'tool_call'
        self.content = content


class LLMProbeError(RuntimeError):
    """Capability probe failure with safe, user-visible stage metadata."""

    def __init__(self, message: str, stages: dict[str, dict]):
        super().__init__(message)
        self.stages = stages


class LLMClient:
    """多供应商 LLM 客户端。

    在线: Anthropic Claude / OpenAI ChatGPT / DeepSeek
    本地: vLLM (OpenAI 兼容接口)
    """

    DEFAULT_MODELS = {
        LLMProvider.CLAUDE: "claude-sonnet-4-6",
        LLMProvider.OPENAI: "gpt-4.1",
        LLMProvider.DEEPSEEK: "deepseek-v4-flash",
    }

    def __init__(self,
                 provider: LLMProvider = LLMProvider.CLAUDE,
                 api_key: str = None,
                 base_url: str = None,
                 model: str = None,
                 max_retries: int = 2,
                 timeout_seconds: int = 60,
                 max_output_tokens: int = 8192,
                 temperature: float | None = None,
                 reasoning_effort: str = "default",
                 thinking_mode: str = "auto",
                 extra_headers: dict[str, str] | None = None,
                 extra_body: dict | None = None):
        self.provider = provider
        self.model = model or self.DEFAULT_MODELS[provider]
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.thinking_mode = thinking_mode
        self.extra_headers = dict(extra_headers or {})
        self.extra_body = dict(extra_body or {})

        if provider == LLMProvider.CLAUDE:
            import anthropic
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            kwargs = {
                "api_key": key,
                "timeout": timeout_seconds,
                "max_retries": 0,
                "default_headers": self.extra_headers or None,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.AsyncAnthropic(**kwargs)
        elif provider == LLMProvider.OPENAI:
            from openai import AsyncOpenAI
            key = api_key or os.getenv("OPENAI_API_KEY")
            kwargs = {
                "api_key": key,
                "base_url": base_url,
                "timeout": timeout_seconds,
                "max_retries": 0,
                "default_headers": self.extra_headers or None,
            }
            self._client = AsyncOpenAI(**kwargs)
        elif provider == LLMProvider.DEEPSEEK:
            from openai import AsyncOpenAI
            key = api_key or os.getenv("DEEPSEEK_API_KEY")
            kwargs = {
                "api_key": key,
                "base_url": base_url or "https://api.deepseek.com/v1",
                "timeout": timeout_seconds,
                "max_retries": 0,
                "default_headers": self.extra_headers or None,
            }
            self._client = AsyncOpenAI(**kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        self._redaction_secrets = [
            value for value in [key, *self.extra_headers.values()] if value
        ]

    def _safe_error_detail(self, exc: Exception) -> str:
        detail = str(exc)
        for secret in getattr(self, "_redaction_secrets", []):
            detail = detail.replace(secret, "[redacted]")
        return re.sub(
            r"(?i)(api[-_ ]?key|authorization|x-api-key)\s*[:=]\s*\S+",
            r"\1=[redacted]", detail,
        )[:500]

    # ── 工具 Schema 格式转换 ──
    @staticmethod
    def _plain(value):
        """Convert SDK response models to JSON-safe dictionaries."""
        if hasattr(value, "model_dump"):
            return value.model_dump(exclude_none=True)
        if isinstance(value, dict):
            return {key: LLMClient._plain(item) for key, item in value.items()}
        if isinstance(value, list):
            return [LLMClient._plain(item) for item in value]
        return value

    @classmethod
    def _clean_parameter_schema(cls, schema: dict, strict: bool) -> dict:
        """Build provider-safe JSON Schema from the registry's UI schema."""
        cleaned = deepcopy(schema or {"type": "object", "properties": {}})

        def visit(node: dict, optional: bool = False) -> dict:
            node = dict(node)
            required_value = node.get("required", [])
            nested_required = set(required_value) if isinstance(required_value, list) else set()
            node.pop("required", None)  # property-level UI flag, not JSON Schema
            properties = node.get("properties")
            if isinstance(properties, dict):
                converted = {}
                for name, child in properties.items():
                    converted[name] = visit(child, strict and name not in nested_required)
                node["properties"] = converted
                node["additionalProperties"] = False
                if strict:
                    node["required"] = list(properties)
                elif nested_required:
                    node["required"] = list(nested_required)
            if "items" in node and isinstance(node["items"], dict):
                node["items"] = visit(node["items"])
            if optional:
                current = node.get("type")
                if isinstance(current, str):
                    node["type"] = [current, "null"]
                elif isinstance(current, list) and "null" not in current:
                    node["type"] = [*current, "null"]
                if "enum" in node and None not in node["enum"]:
                    node["enum"] = [*node["enum"], None]
            return node

        # Preserve root required before the recursive property-level cleanup.
        root_required = list(cleaned.get("required", []))
        properties = cleaned.get("properties", {})
        result = {
            "type": "object",
            "properties": {
                name: visit(child, strict and name not in root_required)
                for name, child in properties.items()
            },
            "additionalProperties": False,
        }
        result["required"] = list(properties) if strict else root_required
        return result

    @classmethod
    def _prepare_tools(cls, tools: list[dict], strict: bool) -> list[dict]:
        prepared = []
        for tool in tools or []:
            item = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": cls._clean_parameter_schema(
                    tool.get("parameters", {}), strict,
                ),
            }
            if strict:
                item["strict"] = True
            prepared.append(item)
        return prepared

    def _to_claude_tools(self, tools: list[dict], strict: bool = True) -> list[dict]:
        """OpenAI-style function definitions → Claude tool definitions."""
        claude_tools = []
        for t in self._prepare_tools(tools, strict):
            converted = {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            if strict:
                converted["strict"] = True
            claude_tools.append(converted)
        return claude_tools

    def _extract_claude_tool_calls(self, content: list) -> list[dict]:
        """从 Claude 响应中提取 tool_use blocks"""
        calls = []
        for block in content:
            if getattr(block, 'type', None) == 'tool_use':
                calls.append({
                    "id": getattr(block, 'id', ''),
                    "name": block.name,
                    "arguments": block.input,
                    "raw_arguments": block.input,
                    "parse_error": "",
                })
        return calls

    def _extract_openai_tool_calls(self, msg) -> list[dict]:
        """从 OpenAI/DeepSeek 响应中提取 tool_calls"""
        calls = []
        for tc in getattr(msg, 'tool_calls', []) or []:
            fn = getattr(tc, 'function', None)
            if fn:
                parse_error = ""
                try:
                    args = json.loads(fn.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    args = {}
                    parse_error = str(exc)
                calls.append({
                    "id": tc.id, "name": fn.name, "arguments": args,
                    "raw_arguments": fn.arguments, "parse_error": parse_error,
                })
        return calls

    @staticmethod
    def _with_deepseek_response_schema(
        messages: list[dict], response_schema: dict | None,
    ) -> list[dict]:
        """Put the schema in-band because DeepSeek JSON mode is not strict."""
        if not response_schema:
            return messages
        enriched = deepcopy(messages)
        properties = response_schema.get("properties", {})
        user_facing = ""
        if "answer_markdown" in properties:
            user_facing = (
                "\n`answer_markdown` 必须包含可直接展示给用户的完整 Markdown 报告。"
                "不要另建 answer、details、trend_summary、methodology、limitations 或 "
                "follow_up_questions 等顶层字段；这些内容必须合并进 answer_markdown，"
                "追问只能写入 followup_suggestions。"
            )
        instruction = (
            "\n\n[DeepSeek JSON 输出契约]\n"
            "只返回一个 JSON 对象，必须逐项符合下面的 JSON Schema；"
            "不得增加 Schema 未声明的顶层字段。不要使用 Markdown 代码围栏。"
            f"{user_facing}\nJSON Schema:\n"
            f"{json.dumps(response_schema, ensure_ascii=False, separators=(',', ':'))}"
        )
        for index in range(len(enriched) - 1, -1, -1):
            message = enriched[index]
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                message["content"] += instruction
                break
        else:
            enriched.append({"role": "user", "content": instruction.strip()})
        return enriched

    # ── 对话接口 ──
    async def chat(self,
                   messages: list[dict],
                   tools: list[dict] = None,
                   max_tokens: int = 8192,
                   tool_choice=None,
                   response_schema: dict | None = None,
                   json_mode: bool = False,
                   strict_tools: bool = True) -> ChatResponse:
        """统一输出预算、重试和供应商错误映射。"""
        max_tokens = min(max_tokens, getattr(self, "max_output_tokens", 8192))
        system_prompt = None
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                chat_messages.append(m)

        for attempt in range(self.max_retries + 1):
            try:
                if self.provider == LLMProvider.CLAUDE:
                    response = await self._claude_chat(
                        system_prompt, chat_messages, tools, max_tokens,
                        tool_choice, response_schema, strict_tools,
                    )
                else:
                    response = await self._openai_chat(
                        system_prompt, chat_messages, tools, max_tokens,
                        tool_choice, response_schema, json_mode, strict_tools,
                    )
                if not response.text.strip() and not response.tool_calls:
                    raise RuntimeError("LLM_EMPTY_RESPONSE")
                return response
            except Exception as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"LLM_PROVIDER_ERROR[{self.provider.value}]: "
                        f"{type(exc).__name__}: {self._safe_error_detail(exc)}"
                    ) from exc
                await asyncio.sleep(0.5 * (2 ** attempt))

    async def _claude_chat(self, system_prompt, messages, tools, max_tokens,
                           tool_choice=None, response_schema=None,
                           strict_tools=True):
        kwargs = {"model": self.model, "max_tokens": max_tokens}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.extra_body:
            kwargs["extra_body"] = deepcopy(self.extra_body)
        if system_prompt:
            kwargs["system"] = system_prompt
        if messages:
            kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = self._to_claude_tools(tools, strict_tools)
        if tool_choice is not None:
            if isinstance(tool_choice, str):
                kwargs["tool_choice"] = {"type": tool_choice}
            else:
                kwargs["tool_choice"] = tool_choice
        if response_schema:
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": response_schema,
                }
            }

        response = await self._client.messages.create(**kwargs)
        text = ""
        for block in response.content:
            if getattr(block, 'type', None) == 'text':
                text += block.text

        tool_calls = self._extract_claude_tool_calls(response.content)
        usage = getattr(response, "usage", None)
        return ChatResponse(
            text=text, tool_calls=tool_calls,
            finish_reason=str(getattr(response, "stop_reason", "") or ""),
            usage={
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
            } if usage else {},
            request_id=str(getattr(response, "id", "") or ""),
            provider=self.provider.value, model=self.model,
            raw_assistant_message={
                "role": "assistant",
                "content": self._plain(response.content),
            },
        )

    async def _openai_chat(self, system_prompt, messages, tools, max_tokens,
                           tool_choice=None, response_schema=None,
                           json_mode=False, strict_tools=True):
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        if self.provider == LLMProvider.DEEPSEEK and response_schema:
            msgs = self._with_deepseek_response_schema(msgs, response_schema)

        kwargs = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        request_extra_body = deepcopy(self.extra_body)
        if self.provider == LLMProvider.DEEPSEEK:
            if self.thinking_mode in {"enabled", "disabled"}:
                request_extra_body["thinking"] = {"type": self.thinking_mode}
            if self.reasoning_effort != "default":
                request_extra_body["reasoning_effort"] = self.reasoning_effort
        elif self.reasoning_effort != "default":
            kwargs["reasoning_effort"] = self.reasoning_effort
        if request_extra_body:
            kwargs["extra_body"] = request_extra_body
        if tools:
            # DeepSeek strict mode is a separate beta endpoint; keep production
            # traffic on local validation even when strict_tools=True.
            provider_strict = strict_tools and self.provider == LLMProvider.OPENAI
            openai_tools = [
                {"type": "function", "function": t}
                for t in self._prepare_tools(tools, provider_strict)
            ]
            kwargs["tools"] = openai_tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if response_schema and self.provider == LLMProvider.OPENAI:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "patent_agent_final",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        elif json_mode or (response_schema and self.provider == LLMProvider.DEEPSEEK):
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        text = msg.content or ""
        tool_calls = self._extract_openai_tool_calls(msg)
        raw_message = self._plain(msg)
        reasoning_content = str(
            getattr(msg, "reasoning_content", "") or
            (raw_message.get("reasoning_content", "") if isinstance(raw_message, dict) else "")
        )
        usage = getattr(response, "usage", None)
        return ChatResponse(
            text=text, tool_calls=tool_calls,
            finish_reason=str(getattr(response.choices[0], "finish_reason", "") or ""),
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            } if usage else {},
            request_id=str(getattr(response, "id", "") or ""),
            provider=self.provider.value, model=self.model,
            raw_assistant_message=raw_message,
            reasoning_content=reasoning_content,
        )

    async def continue_with_tool_results(
        self, base_messages: list[dict], assistant_response: ChatResponse,
        tool_results: list[dict], tools: list[dict], final_instruction: str,
        response_schema: dict | None = None, max_tokens: int = 8192,
    ) -> ChatResponse:
        """Complete one official provider-specific tool round trip."""
        messages = list(base_messages)
        raw = deepcopy(assistant_response.raw_assistant_message)
        if not raw:
            raise RuntimeError("LLM_TOOL_PROTOCOL_ERROR: missing assistant message")
        if self.provider == LLMProvider.CLAUDE:
            messages.append({
                "role": "assistant", "content": raw.get("content", []),
            })
            blocks = []
            for result in tool_results:
                block = {
                    "type": "tool_result",
                    "tool_use_id": result["tool_call_id"],
                    "content": json.dumps(
                        result.get("payload", {}), ensure_ascii=False, default=str,
                    ),
                }
                if result.get("is_error"):
                    block["is_error"] = True
                blocks.append(block)
            # Claude requires all tool_result blocks first in one adjacent user message.
            blocks.append({"type": "text", "text": final_instruction})
            messages.append({"role": "user", "content": blocks})
            return await self.chat(
                messages, tools=tools, tool_choice="none",
                response_schema=response_schema, max_tokens=max_tokens,
            )

        # OpenAI and DeepSeek use assistant + one role=tool message per call.
        raw["role"] = "assistant"
        if self.provider != LLMProvider.DEEPSEEK:
            raw.pop("reasoning_content", None)
        messages.append(raw)
        for result in tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": json.dumps(
                    result.get("payload", {}), ensure_ascii=False, default=str,
                ),
            })
        messages.append({"role": "user", "content": final_instruction})

        if self.provider == LLMProvider.DEEPSEEK:
            # DeepSeek enables thinking mode by default.  That mode supports
            # tool calls, but rejects some explicit tool_choice values.  Once
            # every requested tool result is present, omit the tool catalogue
            # entirely so this request is unambiguously the answer phase.
            # Keep the assistant message above intact: reasoning_content is
            # required by DeepSeek for a thinking-mode tool round trip.
            return await self.chat(
                messages,
                response_schema=response_schema,
                # DeepSeek JSON mode requires an explicit JSON instruction.
                # The normal synthesis path supplies a schema; the probe's
                # plain-text acknowledgement intentionally does not.
                json_mode=response_schema is not None,
                max_tokens=max_tokens,
            )

        return await self.chat(
            messages, tools=tools, tool_choice="none",
            response_schema=response_schema,
            max_tokens=max_tokens,
        )

    async def probe(self) -> dict:
        """Verify text plus a complete, side-effect-free tool round trip."""
        test_tool = {
            "name": "patentagent_connection_echo",
            "description": "Connection probe. Echo the supplied token exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "description": "Must be PA_OK"},
                },
                "required": ["token"],
            },
        }
        base = [{
            "role": "user",
            "content": (
                "连接检查：必须且只能调用 patentagent_connection_echo，"
                "token 必须为 PA_OK；不要直接回答文本。"
            ),
        }]
        if self.provider == LLMProvider.DEEPSEEK:
            # Thinking mode (the DeepSeek default) rejects a named forced
            # function choice.  Omit tool_choice entirely: when tools are
            # present DeepSeek defaults to automatic selection.  The single
            # available tool plus this explicit instruction still verifies a
            # real model -> local tool round trip.
            probe_choice_kwargs = {}
        elif self.provider == LLMProvider.CLAUDE:
            probe_choice_kwargs = {
                "tool_choice": {"type": "tool", "name": test_tool["name"]},
            }
        else:
            probe_choice_kwargs = {
                "tool_choice": {
                    "type": "function", "function": {"name": test_tool["name"]},
                },
            }
        response = await self.chat(
            base, tools=[test_tool], max_tokens=128, **probe_choice_kwargs,
        )
        if len(response.tool_calls) != 1:
            raise RuntimeError("LLM probe did not return exactly one tool call")
        call = response.tool_calls[0]
        if call.get("name") != test_tool["name"] or call.get("arguments", {}).get("token") != "PA_OK":
            raise RuntimeError("LLM probe returned invalid tool parameters")
        final = await self.continue_with_tool_results(
            base, response, [{
                "tool_call_id": call["id"],
                "payload": {"status": "ok", "echo": "PA_OK"},
            }], [test_tool], "用一句话确认工具往返成功。", max_tokens=64,
        )
        if not final.text.strip():
            raise RuntimeError("LLM probe final response was empty")
        probe_schema = {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["PA_OK"]}},
            "required": ["status"],
            "additionalProperties": False,
        }
        structured = await self.chat(
            [{"role": "user", "content": "Return JSON with status exactly PA_OK."}],
            response_schema=probe_schema,
            json_mode=self.provider == LLMProvider.DEEPSEEK,
            max_tokens=64,
        )
        try:
            structured_value = json.loads(structured.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM probe structured output was invalid JSON") from exc
        if structured_value != {"status": "PA_OK"}:
            raise RuntimeError("LLM probe structured output failed schema validation")
        return {
            "provider": self.provider.value,
            "model": self.model,
            "finish_reason": final.finish_reason,
            "tool_roundtrip": True,
            "structured_output": True,
        }

    async def probe_detailed(self) -> dict:
        """Run a user-visible staged probe without mutating Agent state."""
        started = time.perf_counter()
        text_started = time.perf_counter()
        stages: dict[str, dict] = {}
        try:
            text_response = await self.chat(
                [{"role": "user", "content": "仅回复 PA_TEXT_OK。"}],
                max_tokens=32,
            )
            if "PA_TEXT_OK" not in text_response.text:
                raise RuntimeError("LLM probe plain-text response was invalid")
        except Exception as exc:
            stages["text"] = {
                "status": "failed",
                "latency_ms": round((time.perf_counter() - text_started) * 1000, 1),
            }
            raise LLMProbeError(str(exc), stages) from exc
        text_ms = round((time.perf_counter() - text_started) * 1000, 1)
        stages["text"] = {"status": "passed", "latency_ms": text_ms}

        roundtrip_started = time.perf_counter()
        try:
            result = await self.probe()
        except Exception as exc:
            message = str(exc).lower()
            if "structured" in message or "schema" in message or "json" in message:
                stages["tool_selection"] = {"status": "passed"}
                stages["tool_result_roundtrip"] = {"status": "passed"}
                stages["structured_output"] = {"status": "failed"}
            elif "final response" in message or "roundtrip" in message:
                stages["tool_selection"] = {"status": "passed"}
                stages["tool_result_roundtrip"] = {"status": "failed"}
            else:
                stages["tool_selection"] = {"status": "failed"}
            raise LLMProbeError(str(exc), stages) from exc
        roundtrip_ms = round((time.perf_counter() - roundtrip_started) * 1000, 1)
        stages.update({
            "tool_selection": {"status": "passed"},
            "tool_result_roundtrip": {"status": "passed"},
            "structured_output": {"status": "passed"},
        })
        result.update({
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "stages": stages,
            "roundtrip_latency_ms": roundtrip_ms,
        })
        return result

    async def close(self) -> None:
        """Release provider SDK transports when a profile is disconnected."""
        close = getattr(self._client, "close", None)
        if close:
            result = close()
            if hasattr(result, "__await__"):
                await result

    # ── 流式接口 ──
    async def chat_streaming(self,
                             messages: list[dict],
                             tools: list[dict] = None) -> AsyncIterator[ChatEvent]:
        """流式对话（Claude 优先）"""
        system_prompt = None
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                chat_messages.append(m)

        if self.provider == LLMProvider.CLAUDE:
            async for event in self._claude_stream(system_prompt, chat_messages, tools):
                yield event
        else:
            # OpenAI/DeepSeek 流式
            async for event in self._openai_stream(system_prompt, chat_messages, tools):
                yield event

    async def _claude_stream(self, system_prompt, messages, tools):
        kwargs = {"model": self.model, "max_tokens": 8192}
        if system_prompt:
            kwargs["system"] = system_prompt
        if messages:
            kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = self._to_claude_tools(tools)

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield ChatEvent("text_delta", event.delta.text)

    async def _openai_stream(self, system_prompt, messages, tools):
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        kwargs = {"model": self.model, "messages": msgs, "stream": True,
                  "max_tokens": 8192}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield ChatEvent("text_delta", delta.content)
