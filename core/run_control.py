"""실행 단위 취소 신호와 현재 run_id를 관리합니다."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event, Lock
from typing import Iterator


_CURRENT_RUN_ID: ContextVar[str | None] = ContextVar("current_run_id", default=None)
_RUN_CANCEL_EVENTS: dict[str, Event] = {}
_RUN_CANCEL_LOCK = Lock()


class RunCancelledError(RuntimeError):
    """현재 run이 사용자의 요청으로 취소되었음을 나타냅니다."""



def register_run(run_id: str) -> None:
    """run_id에 대한 취소 이벤트를 준비합니다."""

    with _RUN_CANCEL_LOCK:
        _RUN_CANCEL_EVENTS.setdefault(run_id, Event())


def request_stop(run_id: str) -> bool:
    """해당 run_id의 취소 이벤트를 set합니다."""

    with _RUN_CANCEL_LOCK:
        event = _RUN_CANCEL_EVENTS.setdefault(run_id, Event())
        event.set()
    return True


def clear_run(run_id: str) -> None:
    """run_id의 취소 상태를 정리합니다."""

    with _RUN_CANCEL_LOCK:
        _RUN_CANCEL_EVENTS.pop(run_id, None)


def is_stop_requested(run_id: str | None = None) -> bool:
    """현재 run 또는 지정한 run에 취소 요청이 들어왔는지 확인합니다."""

    effective_run_id = run_id or _CURRENT_RUN_ID.get()
    if not effective_run_id:
        return False

    with _RUN_CANCEL_LOCK:
        event = _RUN_CANCEL_EVENTS.get(effective_run_id)
        return bool(event and event.is_set())


def raise_if_stopped(run_id: str | None = None) -> None:
    """취소 요청이 있으면 RunCancelledError를 발생시킵니다."""

    if is_stop_requested(run_id):
        raise RunCancelledError("Run cancelled")


@contextmanager
def use_current_run_id(run_id: str) -> Iterator[str]:
    """현재 실행 중인 run_id를 컨텍스트에 저장합니다."""

    token = _CURRENT_RUN_ID.set(run_id)
    try:
        yield run_id
    finally:
        _CURRENT_RUN_ID.reset(token)