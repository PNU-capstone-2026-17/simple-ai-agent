"""LangGraph checkpoint 저장소를 관리하는 유틸리티입니다.
영속 SQLite checkpoint 파일을 사용해 실행 상태를 보존합니다.
"""

from __future__ import annotations

from datetime import datetime
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver


def _checkpoint_db_path() -> Path:
    """checkpoint SQLite 파일 경로를 반환합니다."""

    raw_path = os.getenv("LANGGRAPH_CHECKPOINT_DB_PATH", "data/checkpoints.sqlite3")
    return Path(raw_path)


@lru_cache(maxsize=1)
def get_checkpoint_store() -> SqliteSaver:
    """영속 checkpoint saver를 반환합니다."""

    db_path = _checkpoint_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


def init_checkpoint_store() -> None:
    """checkpoint 저장소의 테이블을 준비합니다."""

    get_checkpoint_store().setup()


def list_checkpoint_run_ids() -> list[str]:
    """저장된 checkpoint thread_id 목록을 반환합니다."""

    saver = get_checkpoint_store()
    with saver.cursor():
        rows = saver.conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id ASC").fetchall()
    return [str(row[0]) for row in rows]


def get_latest_checkpoint_reference(thread_id: str | None = None) -> tuple[str, str] | None:
    """가장 최근에 생성된 checkpoint의 `(thread_id, checkpoint_id)`를 반환합니다.

    `thread_id`가 주어지면 해당 실행의 최신 checkpoint만 조회합니다.
    """

    latest_reference: tuple[str, str] | None = None
    latest_created_at: datetime | None = None

    thread_ids = [thread_id] if thread_id is not None else list_checkpoint_run_ids()

    for current_thread_id in thread_ids:
        history = get_checkpoint_history(current_thread_id)
        if not history:
            continue

        snapshot = history[0]
        if snapshot.created_at is None:
            continue

        created_at = datetime.fromisoformat(snapshot.created_at)
        if latest_created_at is None or created_at > latest_created_at:
            latest_created_at = created_at
            latest_reference = (
                current_thread_id,
                str(snapshot.config["configurable"]["checkpoint_id"]),
            )

    return latest_reference


def get_checkpointed_state(thread_id: str):
    """주어진 `thread_id`의 최신 checkpoint state를 반환합니다."""

    from graph import build_graph

    app = build_graph()
    return app.get_state({"configurable": {"thread_id": thread_id}})


def get_checkpoint_history(thread_id: str):
    """주어진 `thread_id`의 checkpoint 이력을 최신 순으로 반환합니다."""

    from graph import build_graph

    app = build_graph()
    return list(app.get_state_history({"configurable": {"thread_id": thread_id}}))


def find_checkpoint_before_node(thread_id: str, node_name: str) -> str:
    """주어진 노드가 다음 실행 대상이 되는 checkpoint_id를 찾습니다."""

    for snapshot in get_checkpoint_history(thread_id):
        if node_name in tuple(snapshot.next):
            return str(snapshot.config["configurable"]["checkpoint_id"])
    raise ValueError(f"No checkpoint found before node={node_name!r} for thread_id={thread_id!r}")


def resume_from_checkpoint(thread_id: str, checkpoint_id: str) -> tuple[str, dict[str, Any]]:
    """지정한 checkpoint에서 워크플로우를 재개합니다."""

    history = get_checkpoint_history(thread_id)
    if not any(str(snapshot.config["configurable"]["checkpoint_id"]) == checkpoint_id for snapshot in history):
        raise ValueError(f"No checkpoint found for thread_id={thread_id!r}, checkpoint_id={checkpoint_id!r}")

    from graph import build_graph

    app = build_graph()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
    result = app.invoke(None, config=config)
    return thread_id, result


def resume_from_node(thread_id: str, node_name: str) -> tuple[str, dict[str, Any]]:
    """주어진 노드 직전 checkpoint를 찾아 해당 위치부터 재실행합니다."""

    checkpoint_id = find_checkpoint_before_node(thread_id, node_name)
    return resume_from_checkpoint(thread_id, checkpoint_id)


def resume_run(thread_id: str, checkpoint_id: str | None = None, node_name: str | None = None) -> tuple[str, dict[str, Any]]:
    """checkpoint_id 또는 node_name 기준으로 워크플로우를 재개합니다."""

    if checkpoint_id and node_name:
        raise ValueError("Provide either checkpoint_id or node_name, not both")
    if not checkpoint_id and not node_name:
        raise ValueError("checkpoint_id or node_name is required")

    if checkpoint_id:
        return resume_from_checkpoint(thread_id, checkpoint_id)
    return resume_from_node(thread_id, node_name or "")