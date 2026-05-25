"""파이프라인에서 사용되는 상태 타입과 유틸리티를 정의합니다.
`ProjectState` 타입과 필수값 검증 헬퍼를 포함합니다.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, Optional, TypedDict, cast


StageName = Literal["requirements", "system_design", "development", "coverage"]

STAGE_REQUIREMENTS: StageName = "requirements"
STAGE_SYSTEM_DESIGN: StageName = "system_design"
STAGE_DEVELOPMENT: StageName = "development"
STAGE_COVERAGE: StageName = "coverage"


class StageRuntimeState(TypedDict, total=False):
    current_tc: Optional[str]
    feedback: Optional[str]
    is_passed: Optional[bool]
    retry_count: int


class RequirementsState(StageRuntimeState, total=False):
    req_spec: Optional[str]


class SystemDesignState(StageRuntimeState, total=False):
    sys_diagram: Optional[str]


class DevelopmentState(StageRuntimeState, total=False):
    source_code: Optional[str]


class CoverageState(StageRuntimeState, total=False):
    test_coverage: Optional[str]


class ProjectState(TypedDict):
    functional_req: str
    non_functional_req: str
    run_id: str

    requirements: NotRequired[RequirementsState]
    system_design: NotRequired[SystemDesignState]
    development: NotRequired[DevelopmentState]
    coverage: NotRequired[CoverageState]


MAX_RETRIES = 5

DEFAULT_STAGE_STATE: StageRuntimeState = {
    "current_tc": None,
    "feedback": None,
    "is_passed": None,
    "retry_count": 0,
}


def require_text(value: Optional[str], field_name: str) -> str:
    """필수 문자열 필드가 존재하는지 검사하고 반환합니다.

    `value`가 `None`이면 `ValueError`를 발생시킵니다.
    """

    if value is None:
        raise ValueError(f"{field_name} is required but missing.")
    return value


def get_stage_state(state: ProjectState, stage_name: StageName) -> dict[str, Any]:
    """주어진 `state`에서 특정 `stage_name`의 런타임 상태를 추출하여 반환합니다.

    반환값은 기본값(`DEFAULT_STAGE_STATE`)을 병합한 딕셔너리입니다.
    """

    stage_state = dict(DEFAULT_STAGE_STATE)
    stage_state.update(cast(dict[str, Any], state.get(stage_name, {})))
    return stage_state


def stage_retry_count(state: ProjectState, stage_name: StageName) -> int:
    """주어진 단계의 재시도 카운트를 정수로 반환합니다."""

    return int(get_stage_state(state, stage_name).get("retry_count", 0))


def stage_is_passed(state: ProjectState, stage_name: StageName) -> bool:
    """주어진 단계가 통과되었는지(boolean) 여부를 반환합니다."""

    return bool(get_stage_state(state, stage_name).get("is_passed"))


def update_stage_state(state: ProjectState, stage_name: StageName, **updates: Any) -> dict[str, Any]:
    """특정 단계의 상태를 업데이트하고 병합된 상태 딕셔너리를 반환합니다.

    실제 상태를 변경하지 않고, 업데이트된 단계 상태를 포함하는 딕셔너리를 반환합니다.
    """

    merged_state = get_stage_state(state, stage_name)
    merged_state.update(updates)
    return {stage_name: merged_state}


def normalize_project_state(payload: dict[str, Any]) -> ProjectState:
    """단일-레벨 입력 페이로드를 `ProjectState` 형태로 정규화합니다.

    각 단계별(primary field) 또는 단계 네임스페이스로 주어진 입력을
    `requirements`, `system_design`, `development`, `coverage` 키 아래의
    구조로 재배치합니다.
    """

    normalized = dict(payload)

    stage_field_map: dict[StageName, tuple[str, ...]] = {
        STAGE_REQUIREMENTS: ("req_spec", "current_tc", "feedback", "is_passed", "retry_count"),
        STAGE_SYSTEM_DESIGN: ("sys_diagram", "current_tc", "feedback", "is_passed", "retry_count"),
        STAGE_DEVELOPMENT: ("source_code", "current_tc", "feedback", "is_passed", "retry_count"),
        STAGE_COVERAGE: ("test_coverage", "current_tc", "feedback", "is_passed", "retry_count"),
    }

    for stage_name, field_names in stage_field_map.items():
        stage_state = normalized.get(stage_name, {})
        if not isinstance(stage_state, dict):
            stage_state = {}

        anchor_stage = stage_name if stage_name in normalized or field_names[0] in normalized else None

        primary_field = field_names[0]
        if primary_field in normalized:
            stage_state[primary_field] = normalized.pop(primary_field)

        if anchor_stage is not None:
            for field_name in field_names[1:]:
                if field_name in normalized:
                    stage_state[field_name] = normalized.pop(field_name)

            normalized[stage_name] = {**DEFAULT_STAGE_STATE, **stage_state}

    return cast(ProjectState, normalized)
