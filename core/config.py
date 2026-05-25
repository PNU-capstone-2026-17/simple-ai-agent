"""에이전트별 LLM 구성 로딩 및 환경 변수 치환 유틸리티입니다.
`agent_llm_config.json`을 읽고 에이전트에 맞는 클라이언트와 모델을 반환합니다.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from .llm_types import OpenAIClientProtocol


def _resolve_env_reference(value: Any) -> Any:
    """값이 `${ENV}` 형식으로 주어지면 해당 환경변수로 치환하여 반환합니다.

    문자열이 아닐 경우 원값을 그대로 반환합니다. 참조된 환경변수가 비어있으면 예외를 발생시킵니다.
    """

    if not isinstance(value, str):
        return value

    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1].strip()
        if not env_name:
            return value
        resolved = os.getenv(env_name)
        if resolved is None or not resolved:
            raise RuntimeError(f"Environment variable '{env_name}' referenced by agent LLM config is not set.")
        return resolved

    return value


@lru_cache(maxsize=1)
def _load_agent_llm_map() -> dict[str, dict[str, Any]]:
    """`agent_llm_config.json` 파일을 읽어 에이전트별 LLM 설정 맵을 반환합니다.

    반환 형식: { agent_id: { base_url, api_key, model, ... } }
    """

    config_path = Path(os.getenv("AGENT_LLM_CONFIG_FILE", "agent_llm_config.json"))
    if not config_path.exists():
        return {}

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid agent LLM config JSON: {config_path}") from exc

    if not isinstance(loaded, dict):
        raise RuntimeError("Agent LLM config must be a JSON object keyed by agent name.")

    normalized: dict[str, dict[str, Any]] = {}
    for agent_id, value in loaded.items():
        if isinstance(agent_id, str) and isinstance(value, dict):
            normalized[agent_id] = value
    return normalized


def get_llm_for_agent(agent_id: str) -> tuple[OpenAIClientProtocol, str]:
    """에이전트 ID에 대응하는 LLM 클라이언트와 모델 이름을 반환합니다.

    내부적으로 설정 파일을 로드하고 필요한 필드(base_url, api_key, model)를 검증합니다.
    """

    agent_map = _load_agent_llm_map()
    config = agent_map.get(agent_id) or agent_map.get(agent_id.lower())
    if not config:
        raise RuntimeError(f"LLM config for agent '{agent_id}' was not found.")

    base_url = _resolve_env_reference(config.get("base_url") or config.get("url"))
    api_key = _resolve_env_reference(config.get("api_key") or config.get("key"))
    model = _resolve_env_reference(config.get("model"))

    if not isinstance(base_url, str) or not base_url:
        raise RuntimeError(f"Agent '{agent_id}' is missing a valid base_url.")
    if not isinstance(api_key, str) or not api_key:
        raise RuntimeError(f"Agent '{agent_id}' is missing a valid api_key.")
    if not isinstance(model, str) or not model:
        raise RuntimeError(f"Agent '{agent_id}' is missing a valid model.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai 패키지가 필요합니다.") from exc

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0, max_retries=5)
    return cast(OpenAIClientProtocol, client), model