"""요구사항 분석(Requirements) 관련 에이전트 및 테스트 시스템을 정의합니다.
요구사항 추출, 요구사항 기반 테스트 케이스 생성 및 검증을 처리합니다.
"""

from typing import Any

from core.llm_utils import evaluate_with_llm, generate_json_with_llm
from core.logging import get_logger
from core.state import ProjectState, STAGE_REQUIREMENTS, require_text, update_stage_state

from .prompts import REQ_ANALYSIS_PROMPT, REQ_TC_PROMPT
from .schemas import ReqAnalysisOutput, ReqTcOutput


logger = get_logger(__name__)


def req_analysis_agent(state: ProjectState) -> dict[str, Any]:
    """요구사항 분석 에이전트.

    입력 상태의 기능/비기능 요구사항을 합쳐 LLM에 전달하고,
    검증 가능한 요구사항 JSON을 생성해 저장합니다.
    """

    logger.debug("entering requirements analysis agent")
    functional_req = require_text(state.get("functional_req"), "functional_req")
    non_functional_req = require_text(state.get("non_functional_req"), "non_functional_req")
    requirements_state = state.get(STAGE_REQUIREMENTS, {})
    context = f"기능적 요구사항: {functional_req}\n비기능적 요구사항: {non_functional_req}"
    result = generate_json_with_llm(ReqAnalysisOutput, REQ_ANALYSIS_PROMPT, context, requirements_state.get("feedback"), agent_id="req_analysis_agent")
    return update_stage_state(
        state,
        STAGE_REQUIREMENTS,
        req_spec=result,
        retry_count=int(requirements_state.get("retry_count", 0)) + 1,
        current_tc=requirements_state.get("current_tc"),
        feedback=requirements_state.get("feedback"),
        is_passed=False,
    )


def req_tc_agent(state: ProjectState) -> dict[str, Any]:
    """요구사항 기반 BDD 테스트 케이스를 생성하는 에이전트.

    이전 단계에서 생성된 `req_spec`을 입력으로 받아 테스트 케이스 JSON을 생성합니다.
    """

    requirements_state = state.get(STAGE_REQUIREMENTS, {})
    result = generate_json_with_llm(
        ReqTcOutput,
        REQ_TC_PROMPT,
        require_text(requirements_state.get("req_spec"), "req_spec"),
        requirements_state.get("feedback"),
        agent_id="req_tc_agent",
    )
    return update_stage_state(state, STAGE_REQUIREMENTS, current_tc=result)


def req_testing_system(state: ProjectState) -> dict[str, Any]:
    """요구사항 테스트 시스템.

    생성된 요구사항(`req_spec`)과 테스트 케이스(`current_tc`)를 LLM으로 평가합니다.
    """

    logger.debug("entering req_testing_system")
    requirements_state = state.get(STAGE_REQUIREMENTS, {})
    is_passed, feedback = evaluate_with_llm(
        require_text(requirements_state.get("req_spec"), "req_spec"),
        require_text(requirements_state.get("current_tc"), "current_tc"),
        agent_id="req_testing_system",
    )
    logger.info("req_testing_system result: is_passed=%s, feedback=%s", is_passed, feedback)
    return update_stage_state(state, STAGE_REQUIREMENTS, is_passed=is_passed, feedback=feedback)
