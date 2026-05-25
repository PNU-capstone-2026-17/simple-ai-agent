"""워크플로우 그래프 구성 및 단일 노드 실행을 위한 헬퍼 모듈입니다.
StateGraph을 빌드하고 노드 간 조건부 경로를 정의합니다.
"""

from functools import lru_cache
from typing import Any, Optional

from agents.coverage import coverage_tc_agent, coverage_testing_system, test_agent
from agents.development import dev_agent, dev_tc_agent, dev_testing_system
from agents.requirements import req_analysis_agent, req_tc_agent, req_testing_system
from agents.system_design import sys_design_agent, sys_tc_agent, sys_testing_system
from core.checkpoint import (
    get_checkpoint_history,
    get_checkpoint_store,
    get_checkpointed_state,
    resume_from_checkpoint,
    resume_from_node,
)
from core.state import (
    MAX_RETRIES,
    ProjectState,
    STAGE_COVERAGE,
    STAGE_DEVELOPMENT,
    STAGE_REQUIREMENTS,
    STAGE_SYSTEM_DESIGN,
    normalize_project_state,
    stage_is_passed,
    stage_retry_count,
)
from core.logging import get_logger


END: Any = "__END__"
StateGraph: Any = None
CHECKPOINTER = get_checkpoint_store()
logger = get_logger(__name__)

SINGLE_NODE_REGISTRY: dict[str, Any] = {
    "req_analysis": req_analysis_agent,
    "req_analysis_agent": req_analysis_agent,
    "req_tc_agent": req_tc_agent,
    "req_testing_system": req_testing_system,
    "dev": dev_agent,
    "dev_agent": dev_agent,
}


def route_req(state: ProjectState):
    """요구사항 단계 테스트 결과에 따라 다음 노드를 결정하는 라우팅 함수입니다.

    - `is_passed`가 True면 시스템 설계 노드로 진행합니다.
    - 재시도 한도가 초과하면 종료(END)합니다.
    - 그 외에는 요구사항 분석 노드를 다시 실행합니다.
    """

    if stage_is_passed(state, STAGE_REQUIREMENTS):
        return "sys_design_agent"
    if stage_retry_count(state, STAGE_REQUIREMENTS) >= MAX_RETRIES:
        logger.warning("max retries exceeded; stopping the process.")
        return END
    return "req_analysis_agent"


def route_sys(state: ProjectState):
    """시스템 설계 단계의 라우터.

    `is_passed`가 True이면 개발 단계로, 재시도 한도 초과 시 종료합니다.
    그렇지 않으면 시스템 설계 단계를 다시 실행합니다.
    """

    if stage_is_passed(state, STAGE_SYSTEM_DESIGN):
        return "dev_agent"
    if stage_retry_count(state, STAGE_SYSTEM_DESIGN) >= MAX_RETRIES:
        logger.warning("max retries exceeded; stopping the process.")
        return END
    return "sys_design_agent"


def route_dev(state: ProjectState):
    """개발 단계의 라우터.

    테스트가 통과하면 테스트 에이전트로 진행하고, 재시도 한도 초과 시 종료합니다.
    그렇지 않으면 개발 단계를 재실행합니다.
    """

    if stage_is_passed(state, STAGE_DEVELOPMENT):
        return "test_agent"
    if stage_retry_count(state, STAGE_DEVELOPMENT) >= MAX_RETRIES:
        logger.warning("max retries exceeded; stopping the process.")
        return END
    return "dev_agent"


def route_coverage(state: ProjectState):
    """커버리지 단계 라우터.

    커버리지가 통과되면 워크플로우를 종료하고, 재시도 한도 초과 시에도 종료합니다.
    그렇지 않으면 테스트 에이전트로 이동합니다.
    """

    if stage_is_passed(state, STAGE_COVERAGE):
        return END
    if stage_retry_count(state, STAGE_COVERAGE) >= MAX_RETRIES:
        logger.warning("max retries exceeded; stopping the process.")
        return END
    return "test_agent"


def invoke_single_node(node_name: str, state: ProjectState) -> dict[str, Any]:
    """레지스트리에 등록된 단일 노드를 직접 호출합니다.

    단위 테스트나 디버깅을 위해 특정 노드만 실행할 때 사용됩니다.
    """

    state = normalize_project_state(dict(state))
    try:
        node_callable = SINGLE_NODE_REGISTRY[node_name]
    except KeyError as exc:
        supported = ", ".join(sorted(SINGLE_NODE_REGISTRY))
        raise ValueError(f"Unsupported single node: {node_name}. Supported nodes: {supported}") from exc

    return node_callable(state)


@lru_cache(maxsize=1)
def build_graph():
    """StateGraph을 구성하고 컴파일하여 실행 가능한 워크플로우를 반환합니다.

    이 함수는 langgraph가 설치되어 있어야 정상 동작합니다. 빌드된 워크플로우는
    에이전트 노드들을 연결한 DAG(상태 그래프)입니다.
    """

    global END, StateGraph

    if StateGraph is None:
        try:
            from langgraph.graph import END as langgraph_end, StateGraph as langgraph_state_graph
        except ImportError as exc:
            raise RuntimeError(
                "langgraph is required to build the workflow graph. Install it in the active environment."
            ) from exc

        END = langgraph_end
        StateGraph = langgraph_state_graph

    workflow = StateGraph(ProjectState)

    workflow.add_node("req_analysis_agent", req_analysis_agent)
    workflow.add_node("req_tc_agent", req_tc_agent)
    workflow.add_node("req_testing_system", req_testing_system)
    
    workflow.add_node("sys_design_agent", sys_design_agent)
    workflow.add_node("sys_tc_agent", sys_tc_agent)
    workflow.add_node("sys_testing_system", sys_testing_system)

    workflow.add_node("dev_agent", dev_agent)
    workflow.add_node("dev_tc_agent", dev_tc_agent)
    workflow.add_node("dev_testing_system", dev_testing_system)

    workflow.add_node("test_agent", test_agent)
    workflow.add_node("coverage_tc_agent", coverage_tc_agent)
    workflow.add_node("coverage_testing_system", coverage_testing_system)

    workflow.set_entry_point("req_analysis_agent")

    workflow.add_edge("req_analysis_agent", "req_tc_agent")
    workflow.add_edge("req_tc_agent", "req_testing_system")
    workflow.add_conditional_edges("req_testing_system", route_req)

    workflow.add_edge("sys_design_agent", "sys_tc_agent")
    workflow.add_edge("sys_tc_agent", "sys_testing_system")
    workflow.add_conditional_edges("sys_testing_system", route_sys)

    workflow.add_edge("dev_agent", "dev_tc_agent")
    workflow.add_edge("dev_tc_agent", "dev_testing_system")
    workflow.add_conditional_edges("dev_testing_system", route_dev)

    workflow.add_edge("test_agent", "coverage_tc_agent")
    workflow.add_edge("coverage_tc_agent", "coverage_testing_system")
    workflow.add_conditional_edges("coverage_testing_system", route_coverage)

    return workflow.compile(checkpointer=CHECKPOINTER)


def run_pipeline(initial_state: ProjectState, thread_id: Optional[str] = None) -> tuple[str, dict[str, Any]]:
    """전체 워크플로우를 실행하는 유틸리티.

    `initial_state`와 선택적 `thread_id`를 받아 그래프를 호출하고 최종 상태를 반환합니다.
    """

    from uuid import uuid4

    app = build_graph()
    current_thread_id = thread_id or uuid4().hex
    config = {"configurable": {"thread_id": current_thread_id}}
    result = app.invoke(normalize_project_state(dict(initial_state)), config=config)
    return current_thread_id, result
