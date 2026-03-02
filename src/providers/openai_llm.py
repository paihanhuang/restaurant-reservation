"""OpenAI LLM provider — GPT-4 with function calling."""

from __future__ import annotations

import json
from openai import AsyncOpenAI

from src.providers.base import LLMProvider, LLMResponse


# Function definitions for structured output from the LLM
RESERVATION_FUNCTIONS = [
    {
        "name": "confirm_reservation",
        "description": "Confirm the reservation at the preferred or agreed-upon time.",
        "parameters": {
            "type": "object",
            "properties": {
                "confirmed_time": {
                    "type": "string",
                    "description": "Confirmed time in HH:MM format (24-hour).",
                },
                "confirmed_date": {
                    "type": "string",
                    "description": "Confirmed date in YYYY-MM-DD format.",
                },
            },
            "required": ["confirmed_time", "confirmed_date"],
        },
    },
    {
        "name": "propose_alternative",
        "description": "The restaurant proposed an alternative time. Present it to the system for user approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposed_time": {
                    "type": "string",
                    "description": "Proposed alternative time in HH:MM format (24-hour).",
                },
                "proposed_date": {
                    "type": "string",
                    "description": "Proposed date in YYYY-MM-DD format.",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief reason for the alternative.",
                },
            },
            "required": ["proposed_time"],
        },
    },
    {
        "name": "end_call",
        "description": "End the call — the restaurant cannot accommodate the reservation or the conversation is complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for ending the call.",
                },
                "outcome": {
                    "type": "string",
                    "enum": ["no_availability", "refused", "error", "completed"],
                    "description": "Outcome of the call.",
                },
            },
            "required": ["reason", "outcome"],
        },
    },
]


class OpenAILLM(LLMProvider):
    """GPT-4 chat completion with function calling for structured actions."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        functions: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to GPT-4 and get a response with optional function calls.

        Args:
            messages: Chat history (system + user/assistant turns).
            functions: Available function definitions (defaults to reservation functions).

        Returns:
            LLMResponse with either speech_text or action+params.
        """
        tools = None
        if functions is not None:
            tools = [{"type": "function", "function": f} for f in functions]
        elif functions is None:
            tools = [{"type": "function", "function": f} for f in RESERVATION_FUNCTIONS]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # Low temp for consistent behavior
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # Check if the model wants to call a function
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            return LLMResponse(
                action=tool_call.function.name,
                params=json.loads(tool_call.function.arguments),
                raw_response={"tool_call_id": tool_call.id},
            )

        # Regular text response (speech to restaurant)
        return LLMResponse(
            speech_text=message.content,
        )
