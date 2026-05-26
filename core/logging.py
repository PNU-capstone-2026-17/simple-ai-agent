"""로깅 설정과 편의 로거(인라인 스트림 핸들러)를 제공하는 모듈입니다.
기본 로깅 구성, 이름 기반 로거 생성 및 간단한 인라인 로깅 핸들러를 정의합니다.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections import deque


_STREAM_LOCK = threading.RLock()
_INLINE_LINE_OPEN = False
_INLINE_STREAM_ACTIVE_COUNT = 0
_PENDING_STDOUT_LOGS: deque[tuple[logging.StreamHandler, str]] = deque()


def _flush_pending_logs() -> None:
    """인라인 출력이 종료되면 대기 중인 일반 로그를 순서대로 출력합니다."""

    while _PENDING_STDOUT_LOGS:
        handler, text = _PENDING_STDOUT_LOGS.popleft()
        sys.stdout.write(text)
        sys.stdout.flush()


def begin_inline_stream() -> None:
    """인라인 스트림 세션을 시작합니다."""

    global _INLINE_STREAM_ACTIVE_COUNT
    with _STREAM_LOCK:
        _INLINE_STREAM_ACTIVE_COUNT += 1


def end_inline_stream() -> None:
    """인라인 스트림 세션을 종료하고 대기 로그를 플러시합니다."""

    global _INLINE_LINE_OPEN, _INLINE_STREAM_ACTIVE_COUNT
    with _STREAM_LOCK:
        if _INLINE_STREAM_ACTIVE_COUNT > 0:
            _INLINE_STREAM_ACTIVE_COUNT -= 1

        if _INLINE_STREAM_ACTIVE_COUNT > 0:
            return

        # 인라인 세션 종료 시 출력 경계를 정리한 뒤 일반 로그를 배출합니다.
        if _INLINE_LINE_OPEN:
            sys.stdout.write("\n")
            _INLINE_LINE_OPEN = False
            sys.stdout.flush()

        _flush_pending_logs()


class SyncedStreamHandler(logging.StreamHandler):
    """일반 로그 출력 시 인라인 스트림과 충돌을 방지하는 핸들러입니다."""

    def emit(self, record: logging.LogRecord) -> None:
        global _INLINE_STREAM_ACTIVE_COUNT

        try:
            message = self.format(record)
            with _STREAM_LOCK:
                if _INLINE_STREAM_ACTIVE_COUNT > 0:
                    _PENDING_STDOUT_LOGS.append((self, message + self.terminator))
                    return

                self.stream.write(message + self.terminator)
                self.flush()
        except Exception:
            self.handleError(record)


def setup_logging(level: int = logging.INFO) -> None:
    """프로세스 전역 로깅을 초기화합니다.

    기본 포맷과 스트림을 설정합니다.
    """

    handler = SyncedStreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    logging.basicConfig(level=level, handlers=[handler], force=True)


def get_logger(name: str) -> logging.Logger:
    """이름 기반 표준 로거를 반환합니다."""

    return logging.getLogger(name)


class InlineStreamHandler(logging.StreamHandler):
    """짧은 인라인 메시지 출력용 스트림 핸들러입니다.

    메시지를 줄 단위로 출력하고 버퍼를 플러시합니다. 주로 스트리밍 LLM 출력에 사용됩니다.
    """

    def emit(self, record: logging.LogRecord) -> None:
        global _INLINE_LINE_OPEN

        try:
            message = self.format(record)
            with _STREAM_LOCK:
                sys.stdout.write(message)
                _INLINE_LINE_OPEN = not message.endswith("\n")
                sys.stdout.flush()
        except Exception:
            self.handleError(record)


def get_inline_logger(name: str) -> logging.Logger:
    """간단한 줄 단위 메시지 출력용 로거를 생성/반환합니다.

    동일 이름의 로거가 이미 존재하면 핸들러를 추가하지 않습니다.
    """

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(isinstance(handler, InlineStreamHandler) for handler in logger.handlers):
        handler = InlineStreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    return logger