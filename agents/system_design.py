"""시스템 설계 관련 에이전트와 검증 시스템을 정의합니다.
요구사항으로부터 핵심 컴포넌트와 설계 요약을 생성하고 검증 케이스를 만듭니다.
"""

from typing import Any

from core.llm_utils import evaluate_with_llm, generate_json_with_llm
from core.logging import get_logger
from core.state import ProjectState, STAGE_REQUIREMENTS, STAGE_SYSTEM_DESIGN, require_text, update_stage_state

from .prompts import SYS_DESIGN_PROMPT, SYS_TC_PROMPT
from .schemas import SysDesignOutput, SysTcOutput


logger = get_logger(__name__)


def sys_design_agent(state: ProjectState) -> dict[str, Any]:
    """시스템 설계 에이전트: 요구사항(`req_spec`)으로부터 핵심 컴포넌트와
    데이터 흐름을 요약한 설계 문서를 생성하고 아티팩트로 저장합니다.
    """
    system_design_state = state.get(STAGE_SYSTEM_DESIGN, {})
    requirements_state = state.get(STAGE_REQUIREMENTS, {})
    result = generate_json_with_llm(
        SysDesignOutput,
        SYS_DESIGN_PROMPT,
        require_text(requirements_state.get("req_spec"), "req_spec"),
        system_design_state.get("feedback"),
        agent_id="sys_design_agent",
    )
    return update_stage_state(
        state,
        STAGE_SYSTEM_DESIGN,
        sys_diagram=result,
        retry_count=int(system_design_state.get("retry_count", 0)) + 1,
        current_tc=system_design_state.get("current_tc"),
        feedback=system_design_state.get("feedback"),
        is_passed=False,
    )


def sys_tc_agent(state: ProjectState) -> dict[str, Any]:
    """시스템 설계 기반의 핵심 검증 테스트 케이스(BDD)를 생성합니다."""
    system_design_state = state.get(STAGE_SYSTEM_DESIGN, {})
    result = generate_json_with_llm(
        SysTcOutput,
        SYS_TC_PROMPT,
        require_text(system_design_state.get("sys_diagram"), "sys_diagram"),
        system_design_state.get("feedback"),
        agent_id="sys_tc_agent",
    )
    return update_stage_state(state, STAGE_SYSTEM_DESIGN, current_tc=result)


def sys_testing_system(state: ProjectState) -> dict[str, Any]:
    """시스템 설계 검증 시스템: 설계 문서와 테스트 케이스를 LLM으로 평가합니다.

    평가 결과로 `is_passed`(bool)와 `feedback`(문자열)을 반환합니다.
    """
    logger.debug("entering sys_testing_system")
    system_design_state = state.get(STAGE_SYSTEM_DESIGN, {})
    is_passed, feedback = evaluate_with_llm(
        require_text(system_design_state.get("sys_diagram"), "sys_diagram"),
        require_text(system_design_state.get("current_tc"), "current_tc"),
        agent_id="sys_testing_system",
    )
    logger.info("sys_testing_system result: is_passed=%s, feedback=%s", is_passed, feedback)
    return update_stage_state(state, STAGE_SYSTEM_DESIGN, is_passed=is_passed, feedback=feedback)
