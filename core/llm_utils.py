"""LLM 관련 유틸리티 함수들을 제공하는 모듈입니다.
LLM 호출, 스트리밍 처리, JSON 스키마 유효성 검사 및 평가용 헬퍼를 포함합니다.
"""

from typing import Any, Callable, Optional, TypeVar

import json

from pydantic import BaseModel, ValidationError

from .config import get_llm_for_agent
from .llm_types import OpenAIClientProtocol
from .logging import begin_inline_stream, end_inline_stream, get_inline_logger, get_logger


ProgressCallback = Optional[Callable[[str], None]]
logger = get_logger(__name__)
stream_logger = get_inline_logger(__name__ + ".stream")
T = TypeVar("T", bound=BaseModel)


def _strip_json_fences(content: str) -> str:
    """LLM 응답에서 코드펜스(```json ... ```)를 제거하고 깨끗한 JSON 텍스트를 반환합니다."""

    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _extract_balanced_json(text: str) -> str | None:
    """텍스트에서 첫 번째 균형 잡힌 JSON object/array 구간을 추출합니다."""

    start = -1
    opener = ""
    for idx, ch in enumerate(text):
        if ch in "[{":
            start = idx
            opener = ch
            break

    if start < 0:
        return None

    stack: list[str] = [opener]
    in_string = False
    escaped = False

    for idx in range(start + 1, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "[{":
            stack.append(ch)
            continue

        if ch in "]}":
            if not stack:
                return None
            top = stack[-1]
            if (top == "{" and ch == "}") or (top == "[" and ch == "]"):
                stack.pop()
            else:
                return None

            if not stack:
                return text[start : idx + 1]

    return None


def _extract_delta(chunk: object) -> str | None:
    """스트리밍 청크에서 텍스트 델타(부분 응답)를 추출합니다.

    LangChain/OpenAI 호환 스트리밍 포맷의 `choices[0].delta.content` 또는
    `choices[0].message.content`를 우선적으로 반환합니다.
    """

    choices = getattr(chunk, "choices", None)
    if not choices:
        return None

    first_choice = choices[0]
    delta = getattr(first_choice, "delta", None)
    if delta is not None:
        content = getattr(delta, "content", None)
        if content:
            return content

    message = getattr(first_choice, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content:
            return content

    return None


def _stream_chat_with_logging(
    client: OpenAIClientProtocol,
    model: str,
    messages: list[dict],
    temperature: float,
    agent_id: str,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Stream chat completions with delta logging and synchronous fallback.

    Returns the final concatenated content string.
    """
    begin_inline_stream()
    stream_logger.info("[llm:%s] ", agent_id)
    chunks: list[str] = []
    try:
        try:
            request_kwargs: dict[str, Any] = {
                "model": model,
                "temperature": temperature,
                "stream": True,
                "messages": messages,
            }
            if response_format is not None:
                request_kwargs["response_format"] = response_format

            stream = client.chat.completions.create(**request_kwargs)
            for chunk in stream:
                delta = _extract_delta(chunk)
                if not delta:
                    continue
                chunks.append(delta)
                stream_logger.info(delta)
        except Exception:
            chunks = []

        content: str | None = "".join(chunks).strip() if chunks else None
        if not content:
            request_kwargs = {
                "model": model,
                "temperature": temperature,
                "messages": messages,
            }
            if response_format is not None:
                request_kwargs["response_format"] = response_format

            try:
                response = client.chat.completions.create(**request_kwargs)
            except Exception:
                response = client.chat.completions.create(model=model, temperature=temperature, messages=messages)
            content = getattr(response.choices[0].message, "content", None)

        if content is None:
            raise RuntimeError("LLM 응답 content가 비어 있습니다.")

        return content.strip()
    finally:
        end_inline_stream()


def generate_with_llm(
    role_prompt: str,
    context: str,
    feedback: Optional[str] = None,
    agent_id: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """LLM을 호출해 자유 텍스트 응답을 스트리밍으로 수집해서 반환합니다.

    Args:
        role_prompt: 역할 기반 프롬프트 템플릿
        context: 프롬프트에 주입할 컨텍스트
        feedback: 이전 피드백(선택)
        agent_id: 에이전트 식별자(LLM 설정 조회용)
    Returns:
        LLM이 반환한 전체 텍스트 응답
    """

    prompt_text = f"{role_prompt}\n\n[주어진 정보]\n{context}"
    if feedback and feedback != "Pass":
        prompt_text += f"\n\n[이전 테스트 실패 피드백 - 이를 반영하여 수정하세요]\n{feedback}"

    if not agent_id:
        raise RuntimeError("agent_id is required for agent-scoped LLM configuration.")

    logger.debug("OpenAI-compatible API call started for agent %s.", agent_id)
    client, model = get_llm_for_agent(agent_id)

    messages = [
        {"role": "system", "content": "Return only the requested content."},
        {"role": "user", "content": prompt_text},
    ]

    # Use shared streaming helper (with synchronous fallback)
    content = _stream_chat_with_logging(
        client,
        model,
        messages,
        temperature=0.2,
        agent_id=agent_id,
        response_format=response_format,
    )
    logger.debug("API response received for agent %s.", agent_id)
    return content


def generate_json_with_llm(
    schema_model: type[T],
    role_prompt: str,
    context: str,
    feedback: Optional[str] = None,
    agent_id: str | None = None,
) -> str:
    """스키마를 기반으로 LLM에 JSON 출력을 요청하고 검증된 JSON 문자열을 반환합니다.

    Pydantic 모델(`schema_model`)로 결과를 검증하며, 스키마 불일치 시 예외를 발생시킵니다.
    """

    schema_keys = ", ".join(schema_model.model_fields.keys())
    json_prompt = (
        f"{role_prompt}\n\n"
        f"반드시 JSON object만 출력하세요. 허용 키: {schema_keys}.\n"
        f"주석, 코드펜스, 설명문은 금지합니다."
    )
    raw_content = generate_with_llm(
        json_prompt,
        context,
        feedback=feedback,
        agent_id=agent_id,
        response_format={"type": "json_object"},
    )
    cleaned = _strip_json_fences(raw_content)

    # Recover JSON when model adds prose around the object/array.
    try:
        json.loads(cleaned)
    except Exception:
        candidate = _extract_balanced_json(cleaned)
        if candidate is not None:
            cleaned = candidate

    # Fallback: if schema expects a single string field and model returned plain text,
    # wrap it into that field to keep the pipeline resilient.
    model_fields = schema_model.model_fields
    if len(model_fields) == 1:
        only_key = next(iter(model_fields))
        try:
            loaded = json.loads(cleaned)
        except Exception:
            loaded = None

        if not isinstance(loaded, dict):
            cleaned = json.dumps({only_key: cleaned}, ensure_ascii=False)

    try:
        parsed = schema_model.model_validate_json(cleaned)
    except ValidationError as exc:
        raise RuntimeError(f"LLM JSON output does not match schema for {schema_model.__name__}.") from exc
    return parsed.model_dump_json(indent=2)


def evaluate_with_llm(target: str, test_cases: str, agent_id: str | None = None) -> tuple[bool, str]:
    """LLM을 사용해 산출물(`target`)이 주어진 테스트 케이스(`test_cases`)를 통과하는지 평가합니다.

    반환값은 (성공여부, 결과메시지)로, 성공이면 ('Pass') 형태의 메시지를 반환합니다.
    """
    prompt = f"""
    당신은 엄격한 QA 엔지니어입니다. 아래의 [산출물]이 [테스트 케이스]를 모두 만족하는지 평가하세요.
    완벽하게 만족한다면 오직 'PASS' 라고만 출력하세요.
    부족한 점이 있다면 'FAIL: [구체적인 이유]' 형태로 출력하세요.

    [테스트 케이스]
    {test_cases}

    [산출물]
    {target}
    """
    if not agent_id:
        raise RuntimeError("agent_id is required for agent-scoped LLM configuration.")

    client, model = get_llm_for_agent(agent_id)
    logger.debug("Evaluation request started for agent %s.", agent_id)

    messages = [
        {"role": "system", "content": "You are a strict QA engineer."},
        {"role": "user", "content": prompt},
    ]

    content = _stream_chat_with_logging(client, model, messages, temperature=0, agent_id=agent_id)
    response_text = content.strip()
    logger.debug("Evaluation response received for agent %s.", agent_id)
    if response_text.upper().startswith("PASS"):
        return True, "Pass"
    return False, response_text
