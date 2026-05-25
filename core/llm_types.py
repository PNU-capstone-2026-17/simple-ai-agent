from __future__ import annotations

from typing import Any, Iterable, Protocol, overload, Literal, Optional


class Delta(Protocol):
    content: Optional[str]


class Message(Protocol):
    content: Optional[str]


class ChunkChoice(Protocol):
    delta: Optional[Delta]
    message: Optional[Message]


class Chunk(Protocol):
    choices: list[ChunkChoice]


class ResponseChoice(Protocol):
    message: Message


class ChatCompletionsCreateReturn(Protocol):
    choices: list[ResponseChoice]


class ChatCompletionsInterface(Protocol):
    @overload
    def create(self, *, model: str, temperature: float, messages: list[dict], stream: Literal[True]) -> Iterable[Chunk]:
        ...

    @overload
    def create(self, *, model: str, temperature: float, messages: list[dict], stream: Literal[False] = False) -> ChatCompletionsCreateReturn:
        ...



class ChatInterface(Protocol):
    completions: ChatCompletionsInterface


class OpenAIClientProtocol(Protocol):
    """Minimal protocol describing the OpenAI client used in this project.

    It only requires a `.chat.completions.create(...)` callable that either
    returns an iterable of streaming chunks when `stream=True`, or a sync
    response object having a `choices` attribute when `stream=False`.
    """

    chat: ChatInterface
