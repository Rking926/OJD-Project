"""Abstraction LLM : même interface pour l'API Claude (cloud) et Ollama (local).

L'utilisateur choisit son fournisseur dans les paramètres. Le reste de
l'app (orchestrator.py) ne connaît que `LLMProvider.chat(messages, tools)`.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str  # "tool_use" | "end" | "error"


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict], system: str) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def assistant_tool_use_message(self, response: LLMResponse) -> dict:
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        out = []
        for t in tools:
            out.append({
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            })
        return out

    def chat(self, messages: list[dict], tools: list[dict], system: str) -> LLMResponse:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=messages,
            tools=self._to_anthropic_tools(tools) if tools else [],
        )
        text_parts = []
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        return LLMResponse(text="\n".join(text_parts), tool_calls=tool_calls, stop_reason=resp.stop_reason)

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": content}],
        }

    def assistant_tool_use_message(self, response: LLMResponse) -> dict:
        blocks = []
        if response.text:
            blocks.append({"type": "text", "text": response.text})
        for tc in response.tool_calls:
            blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
        return {"role": "assistant", "content": blocks}


class OllamaProvider(LLMProvider):
    """Fournisseur local via Ollama (ex: llama3.1, qwen2.5) — pas de données envoyées à l'extérieur."""

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        import httpx

        self._model = model
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=120)

    def _to_ollama_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def chat(self, messages: list[dict], tools: list[dict], system: str) -> LLMResponse:
        payload_messages = [{"role": "system", "content": system}] + messages
        resp = self._http.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": payload_messages,
                "tools": self._to_ollama_tools(tools) if tools else [],
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        text = msg.get("content", "") or ""
        tool_calls = []
        for i, tc in enumerate(msg.get("tool_calls", []) or []):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(id=str(i), name=fn.get("name", ""), arguments=args))
        stop_reason = "tool_use" if tool_calls else "end"
        return LLMResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        return {"role": "tool", "content": content}

    def assistant_tool_use_message(self, response: LLMResponse) -> dict:
        return {"role": "assistant", "content": response.text}


def build_provider(config: dict) -> LLMProvider:
    provider = config.get("llm_provider", "anthropic")
    if provider == "anthropic":
        api_key = config.get("anthropic_api_key")
        if not api_key:
            raise ValueError("Clé API Anthropic manquante dans les paramètres.")
        return AnthropicProvider(api_key=api_key, model=config.get("anthropic_model", "claude-sonnet-4-5"))
    if provider == "ollama":
        return OllamaProvider(
            model=config.get("ollama_model", "llama3.1"),
            base_url=config.get("ollama_base_url", "http://localhost:11434"),
        )
    raise ValueError(f"Fournisseur LLM inconnu: {provider}")
