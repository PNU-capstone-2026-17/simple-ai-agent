"""개발 단계 에이전트와 관련 테스트 시스템을 정의합니다.
코드 생성(`dev_agent`), 생성된 코드에 대한 테스트 케이스 생성(`dev_tc_agent`),
그리고 테스트 평가(`dev_testing_system`)를 담당합니다.
"""

from typing import Any

from core.llm_utils import evaluate_with_llm, generate_json_with_llm
from core.state import ProjectState, STAGE_DEVELOPMENT, STAGE_SYSTEM_DESIGN, require_text, update_stage_state

from .prompts import DEV_PROMPT, DEV_TC_PROMPT
from .schemas import DevOutput, DevTcOutput


def dev_agent(state: ProjectState) -> dict[str, Any]:
    """개발 에이전트: 시스템 설계(`sys_diagram`)를 바탕으로 소스코드를 생성합니다.

    생성된 소스는 아티팩트로 저장됩니다.
    """

    development_state = state.get(STAGE_DEVELOPMENT, {})
    system_design_state = state.get(STAGE_SYSTEM_DESIGN, {})
    result = generate_json_with_llm(
        DevOutput,
        DEV_PROMPT,
        require_text(system_design_state.get("sys_diagram"), "sys_diagram"),
        development_state.get("feedback"),
        agent_id="dev_agent",
    )
    return update_stage_state(
        state,
        STAGE_DEVELOPMENT,
        source_code=result,
        retry_count=int(development_state.get("retry_count", 0)) + 1,
        current_tc=development_state.get("current_tc"),
        feedback=development_state.get("feedback"),
        is_passed=False,
    )


def dev_tc_agent(state: ProjectState) -> dict[str, Any]:
    """생성된 소스코드에 대한 PyTest 유닛 테스트 케이스를 생성합니다."""

    development_state = state.get(STAGE_DEVELOPMENT, {})
    result = generate_json_with_llm(
        DevTcOutput,
        DEV_TC_PROMPT,
        require_text(development_state.get("source_code"), "source_code"),
        development_state.get("feedback"),
        agent_id="dev_tc_agent",
    )
    return update_stage_state(state, STAGE_DEVELOPMENT, current_tc=result)


def dev_testing_system(state: ProjectState) -> dict[str, Any]:
    """개발 테스트 시스템: 생성된 소스코드와 테스트 케이스를 평가합니다.

    LLM 평가 결과를 기반으로 `is_passed`와 `feedback`을 반환합니다.
    """

    development_state = state.get(STAGE_DEVELOPMENT, {})
    is_passed, feedback = evaluate_with_llm(
        require_text(development_state.get("source_code"), "source_code"),
        require_text(development_state.get("current_tc"), "current_tc"),
        agent_id="dev_testing_system",
    )
    return update_stage_state(state, STAGE_DEVELOPMENT, is_passed=is_passed, feedback=feedback)
