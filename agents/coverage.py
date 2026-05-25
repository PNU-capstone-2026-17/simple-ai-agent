"""테스트 커버리지 분석 및 관련 테스트 케이스 생성을 담당하는 모듈입니다.
테스트 산출물 분석과 보완을 위한 케이스를 생성합니다.
"""

from typing import Any

from core.llm_utils import evaluate_with_llm, generate_json_with_llm
from core.logging import get_logger
from core.state import ProjectState, STAGE_COVERAGE, STAGE_DEVELOPMENT, require_text, update_stage_state

from .prompts import COVERAGE_PROMPT, COVERAGE_TC_PROMPT
from .schemas import CoverageOutput, CoverageTcOutput


logger = get_logger(__name__)


def test_agent(state: ProjectState) -> dict[str, Any]:
    """테스트 커버리지 분석 에이전트.

    소스코드와 현재 유닛 테스트를 분석해 커버리지 관련 산출물을 생성합니다.
    """

    development_state = state.get(STAGE_DEVELOPMENT, {})
    coverage_state = state.get(STAGE_COVERAGE, {})
    context = (
        f"소스코드:\n{require_text(development_state.get('source_code'), 'source_code')}"
        f"\n\n유닛 테스트코드:\n{require_text(development_state.get('current_tc'), 'current_tc')}"
    )
    result = generate_json_with_llm(CoverageOutput, COVERAGE_PROMPT, context, coverage_state.get("feedback"), agent_id="test_agent")
    return update_stage_state(
        state,
        STAGE_COVERAGE,
        test_coverage=result,
        retry_count=int(coverage_state.get("retry_count", 0)) + 1,
        current_tc=coverage_state.get("current_tc"),
        feedback=coverage_state.get("feedback"),
        is_passed=False,
    )


def coverage_tc_agent(state: ProjectState) -> dict[str, Any]:
    """커버리지 기반 통합 테스트 케이스를 생성합니다."""

    coverage_state = state.get(STAGE_COVERAGE, {})
    result = generate_json_with_llm(
        CoverageTcOutput,
        COVERAGE_TC_PROMPT,
        require_text(coverage_state.get("test_coverage"), "test_coverage"),
        coverage_state.get("feedback"),
        agent_id="coverage_tc_agent",
    )
    return update_stage_state(state, STAGE_COVERAGE, current_tc=result)


def coverage_testing_system(state: ProjectState) -> dict[str, Any]:
    """커버리지 테스트 시스템: coverage 분석 결과와 생성된 통합 테스트 케이스를 평가합니다."""

    logger.debug("entering coverage_testing_system")
    coverage_state = state.get(STAGE_COVERAGE, {})
    is_passed, feedback = evaluate_with_llm(
        require_text(coverage_state.get("test_coverage"), "test_coverage"),
        require_text(coverage_state.get("current_tc"), "current_tc"),
        agent_id="coverage_testing_system",
    )
    logger.info("coverage_testing_system result: is_passed=%s, feedback=%s", is_passed, feedback)
    return update_stage_state(state, STAGE_COVERAGE, is_passed=is_passed, feedback=feedback)
