"""checkpoint 기반 저장/조회 헬퍼를 제공합니다.
아티펙트 조회, 최신 아티펙트 검색 및 워크플로우 실행 헬퍼를 포함합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from core.checkpoint import init_checkpoint_store, list_checkpoint_run_ids
from core.state import normalize_project_state
from core.storage.base import ArtifactRecord


_ARTIFACT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("requirements", "req_spec", "req_analysis_agent"),
    ("requirements", "current_tc", "req_tc_agent"),
    ("system_design", "sys_diagram", "sys_design_agent"),
    ("system_design", "current_tc", "sys_tc_agent"),
    ("development", "source_code", "dev_agent"),
    ("development", "current_tc", "dev_tc_agent"),
    ("coverage", "test_coverage", "test_agent"),
    ("coverage", "current_tc", "coverage_tc_agent"),
)


def init_db() -> None:
    """checkpoint 저장소를 초기화합니다.

    애플리케이션 시작 시 호출하여 checkpoint SQLite 테이블을 준비합니다.
    """

    init_checkpoint_store()


def _snapshot_artifact_records(run_id: str) -> list[ArtifactRecord]:
    """checkpoint history를 아티펙트 레코드 목록으로 변환합니다."""

    from graph import build_graph

    app = build_graph()
    history = list(app.get_state_history({"configurable": {"thread_id": run_id}}))

    records: list[ArtifactRecord] = []
    last_seen: dict[tuple[str, str], str] = {}
    artifact_id = 0

    for snapshot in reversed(history):
        values = snapshot.values
        if not isinstance(values, dict):
            continue

        created_at = datetime.fromisoformat(snapshot.created_at) if snapshot.created_at else datetime.now(timezone.utc)

        for stage_name, artifact_key, source_node in _ARTIFACT_SPECS:
            stage_state = values.get(stage_name, {})
            if not isinstance(stage_state, dict):
                continue

            content = stage_state.get(artifact_key)
            if content is None:
                continue

            normalized_content = content if isinstance(content, str) else str(content)
            marker = (stage_name, artifact_key)
            if last_seen.get(marker) == normalized_content:
                continue

            last_seen[marker] = normalized_content
            artifact_id += 1
            records.append(
                ArtifactRecord(
                    artifact_id=artifact_id,
                    run_id=run_id,
                    source_node=source_node,
                    artifact_key=artifact_key,
                    content=normalized_content,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    return records


def list_saved_artifacts(run_id: str) -> list[ArtifactRecord]:
    """주어진 `run_id`에 해당하는 checkpoint 기반 아티펙트 목록을 반환합니다."""

    return _snapshot_artifact_records(run_id)


def get_latest_artifact(run_id: str, artifact_key: Optional[str] = None) -> Optional[ArtifactRecord]:
    """`run_id`와 선택적 `artifact_key`로 최신 checkpoint 아티펙트를 조회합니다.

    반환값이 없을 수 있으므로 `Optional`을 사용합니다.
    """

    records = list_saved_artifacts(run_id)
    if artifact_key is None:
        return records[-1] if records else None

    for record in reversed(records):
        if record.artifact_key == artifact_key:
            return record
    return None


def list_run_ids() -> list[str]:
    """저장된 모든 실행(run_id) 목록을 반환합니다."""

    return list_checkpoint_run_ids()


def run_project(initial_state: dict[str, Any], run_id: Optional[str] = None) -> tuple[str, dict[str, Any]]:
    """주어진 초기 상태로 워크플로우를 실행하고 최종 상태를 반환합니다.

    `run_id`가 주어지지 않으면 새 UUID를 생성합니다. 내부적으로 `graph.build_graph`
    를 사용해 컴파일된 StateGraph 인스턴스를 호출합니다.
    """

    from graph import build_graph

    app = build_graph()
    current_run_id = run_id or uuid4().hex
    payload = dict(initial_state)
    payload["run_id"] = current_run_id
    config = {"configurable": {"thread_id": current_run_id}}
    result = app.invoke(normalize_project_state(payload), config=config)
    return current_run_id, result
