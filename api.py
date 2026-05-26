"""간단한 FastAPI 기반 아티팩트 조회 및 파이프라인 실행용 API입니다.
런 생성, checkpoint 조회, 아티팩트 조회, 헬스체크 엔드포인트를 제공합니다.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse
from dotenv import load_dotenv

from core.checkpoint import get_checkpoint_history, get_latest_checkpoint_reference, resume_run as resume_checkpoint_run
from core.db import ArtifactRecord, get_latest_artifact, init_db, list_run_ids, list_saved_artifacts, run_project
from core.run_control import clear_run, is_stop_requested, request_stop, use_current_run_id


@asynccontextmanager
async def lifespan(_: FastAPI):
    """애플리케이션 시작 시 환경변수와 저장소를 초기화합니다."""

    load_dotenv()
    init_db()
    yield


app = FastAPI(title="simple-ai-agent artifact api", lifespan=lifespan)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/", include_in_schema=False)
def read_frontend_index() -> FileResponse:
    """프론트엔드 콘솔 페이지를 반환합니다."""

    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend assets not found")
    return FileResponse(str(FRONTEND_DIR / "index.html"))


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


def _to_sse_message(data: str, event: Optional[str] = None) -> str:
    """SSE 형식의 메시지 문자열을 생성합니다."""

    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")

    payload_lines = data.splitlines() or [""]
    lines.extend(f"data: {line}" for line in payload_lines)
    return "\n".join(lines) + "\n\n"


def _run_with_sse_stream(request: "RunRequest"):
    """그래프 실행 중 생성되는 로그를 SSE로 스트리밍합니다."""

    log_queue: Queue[dict[str, str]] = Queue()
    completion_event = Event()
    result_holder: dict[str, object] = {}
    current_run_id = request.run_id or uuid4().hex
    is_resume = request.run_id is not None

    class _QueueTee:
        """원래 스트림으로 쓰면서 SSE 큐에도 동일한 텍스트를 복제합니다."""

        def __init__(self, original_stream) -> None:
            self._original_stream = original_stream

        def write(self, text: str) -> int:
            if text:
                self._original_stream.write(text)
                self._original_stream.flush()
                log_queue.put({"source": "stdout", "text": text})
            return len(text)

        def flush(self) -> None:
            self._original_stream.flush()

        def isatty(self) -> bool:
            return bool(getattr(self._original_stream, "isatty", lambda: False)())

        @property
        def encoding(self):
            return getattr(self._original_stream, "encoding", None)

    class _QueueLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                log_queue.put({"source": "logger", "text": self.format(record) + "\n"})
            except Exception:
                # 로깅 실패가 실행 자체를 중단시키지 않도록 무시합니다.
                return

    handler = _QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    def _worker() -> None:
        tee_stdout = _QueueTee(sys.stdout)
        tee_stderr = _QueueTee(sys.stderr)

        try:
            with use_current_run_id(current_run_id), redirect_stdout(tee_stdout), redirect_stderr(tee_stderr):
                if is_resume:
                    latest_reference = get_latest_checkpoint_reference(current_run_id)
                    if latest_reference is None:
                        raise ValueError(f"No checkpoint found for run_id={current_run_id}")

                    run_id, final_state = resume_checkpoint_run(current_run_id, latest_reference[1])
                else:
                    run_id, final_state = run_project(
                        {
                            "functional_req": request.functional_req,
                            "non_functional_req": request.non_functional_req,
                        },
                        current_run_id,
                    )
            result_holder["run_id"] = run_id
            result_holder["final_state"] = final_state
        except Exception as exc:  # pragma: no cover - 런타임 예외 전달
            result_holder["error"] = str(exc)
        finally:
            clear_run(current_run_id)
            completion_event.set()

    worker = Thread(target=_worker, daemon=True)
    worker.start()

    start_message = "resume started" if is_resume else "run started"
    yield _to_sse_message(json.dumps({"run_id": current_run_id, "message": start_message}, ensure_ascii=False), event="status")

    try:
        while True:
            if is_stop_requested(current_run_id):
                yield _to_sse_message(json.dumps({"run_id": current_run_id, "message": "run cancelled"}, ensure_ascii=False), event="cancelled")
                return

            try:
                message = log_queue.get(timeout=0.2)
                yield _to_sse_message(json.dumps(message, ensure_ascii=False), event="log")
            except Empty:
                pass

            if completion_event.is_set() and log_queue.empty():
                break

        error = result_holder.get("error")
        if isinstance(error, str):
            yield _to_sse_message(json.dumps({"error": error}, ensure_ascii=False), event="error")
            return

        run_id = str(result_holder.get("run_id", ""))
        final_state = result_holder.get("final_state")
        final_state_keys = sorted(final_state.keys()) if isinstance(final_state, dict) else []
        done_payload = json.dumps(
            {
                "run_id": run_id,
                "final_state_keys": final_state_keys,
            },
            ensure_ascii=False,
        )
        yield _to_sse_message(done_payload, event="done")
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)


@app.post("/runs/stream")
def create_run_stream(request: RunRequest) -> StreamingResponse:
    """그래프 실행 로그를 SSE(`text/event-stream`)로 실시간 전달합니다."""

    return StreamingResponse(
        _run_with_sse_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict[str, str]:
    """실행 중인 run에 취소 신호를 보냅니다."""

    request_stop(run_id)
    return {"run_id": run_id, "status": "stopping"}


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
