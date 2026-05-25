"""간단한 FastAPI 기반 아티팩트 조회 및 파이프라인 실행용 API입니다.
런 생성, checkpoint 조회, 아티팩트 조회, 헬스체크 엔드포인트를 제공합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.checkpoint import get_checkpoint_history, resume_run as resume_checkpoint_run
from core.db import ArtifactRecord, get_latest_artifact, init_db, list_run_ids, list_saved_artifacts, run_project


app = FastAPI(title="simple-ai-agent artifact api")


class ArtifactResponse(BaseModel):
    artifact_id: int
    run_id: str
    source_node: str
    artifact_key: str
    content: str
    created_at: datetime
    updated_at: datetime


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse] = Field(default_factory=list)


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    created_at: datetime
    metadata: dict[str, object]
    next: list[str]
    values: dict[str, object]


class CheckpointListResponse(BaseModel):
    items: list[CheckpointResponse] = Field(default_factory=list)


def _to_response(record: ArtifactRecord) -> ArtifactResponse:
    """`ArtifactRecord`를 `ArtifactResponse` Pydantic 모델로 변환합니다."""

    return ArtifactResponse.model_validate(record.__dict__)


def _checkpoint_snapshot_to_response(snapshot) -> CheckpointResponse:
    """LangGraph checkpoint snapshot을 API 응답 형식으로 변환합니다."""

    checkpoint_id = str(snapshot.config["configurable"]["checkpoint_id"])
    return CheckpointResponse(
        checkpoint_id=checkpoint_id,
        created_at=datetime.fromisoformat(snapshot.created_at),
        metadata=dict(snapshot.metadata),
        next=list(snapshot.next),
        values=dict(snapshot.values) if isinstance(snapshot.values, dict) else {"value": snapshot.values},
    )


@app.on_event("startup")
def startup_event() -> None:
    """애플리케이션 시작 시 실행되는 이벤트로 아티팩트 저장소를 초기화합니다."""

    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    """간단한 헬스체크 엔드포인트입니다."""

    return {"status": "ok"}


class RunRequest(BaseModel):
    functional_req: str
    non_functional_req: str
    run_id: Optional[str] = None


class RunResponse(BaseModel):
    run_id: str
    final_state: dict[str, object]


class ResumeRequest(BaseModel):
    checkpoint_id: Optional[str] = None
    node_name: Optional[str] = None


@app.post("/runs", response_model=RunResponse)
def create_run(request: RunRequest) -> RunResponse:
    """새로운 파이프라인 실행을 시작하고 최종 상태를 반환합니다.

    요청의 요구사항을 기반으로 `run_project`를 호출합니다.
    """

    run_id, final_state = run_project(
        {
            "functional_req": request.functional_req,
            "non_functional_req": request.non_functional_req,
        },
        request.run_id,
    )
    return RunResponse(run_id=run_id, final_state=final_state)


@app.get("/runs", response_model=list[str])
def list_runs() -> list[str]:
    """저장된 실행(`run_id`) 목록을 반환합니다."""

    return list_run_ids()


@app.get("/runs/{run_id}/checkpoints", response_model=CheckpointListResponse)
def read_checkpoints(run_id: str) -> CheckpointListResponse:
    """주어진 `run_id`의 checkpoint 이력을 반환합니다."""

    snapshots = list(get_checkpoint_history(run_id))
    return CheckpointListResponse(items=[_checkpoint_snapshot_to_response(snapshot) for snapshot in snapshots])


@app.post("/runs/{run_id}/resume", response_model=RunResponse)
def resume_run(run_id: str, request: ResumeRequest) -> RunResponse:
    """주어진 checkpoint 또는 노드 이름 기준으로 실행을 재개합니다."""

    if request.checkpoint_id and request.node_name:
        raise HTTPException(status_code=400, detail="Provide either checkpoint_id or node_name, not both")
    if not request.checkpoint_id and not request.node_name:
        raise HTTPException(status_code=400, detail="checkpoint_id or node_name is required")

    try:
        resumed_run_id, final_state = resume_checkpoint_run(run_id, request.checkpoint_id, request.node_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RunResponse(run_id=resumed_run_id, final_state=final_state)


@app.get("/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
def read_artifacts(run_id: str) -> ArtifactListResponse:
    """주어진 `run_id`에 대한 모든 아티팩트를 반환합니다."""

    records = list_saved_artifacts(run_id)
    return ArtifactListResponse(items=[_to_response(record) for record in records])


@app.get("/runs/{run_id}/artifacts/latest", response_model=ArtifactResponse)
def read_latest_artifact_for_run(run_id: str) -> ArtifactResponse:
    """주어진 `run_id`의 최신 아티팩트를 반환합니다. 없으면 404를 반환합니다."""

    record = get_latest_artifact(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No artifacts found for run_id={run_id}")
    return _to_response(record)


@app.get("/runs/{run_id}/artifacts/{artifact_key}", response_model=ArtifactResponse)
def read_artifact_by_key(run_id: str, artifact_key: str) -> ArtifactResponse:
    """주어진 `run_id`와 `artifact_key`에 해당하는 최신 아티팩트를 반환합니다."""

    record = get_latest_artifact(run_id, artifact_key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No artifacts found for run_id={run_id}, artifact_key={artifact_key}")
    return _to_response(record)
