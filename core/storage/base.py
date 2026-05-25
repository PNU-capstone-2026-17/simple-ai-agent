"""아티팩트 저장소의 기본 타입과 추상(프로토콜)을 정의합니다.
`ArtifactRecord`와 `ArtifactStore` 인터페이스를 포함합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ArtifactRecord:
    """아티팩트 레코드를 표현하는 불변 데이터 클래스입니다."""

    artifact_id: int
    run_id: str
    source_node: str
    artifact_key: str
    content: str
    created_at: datetime
    updated_at: datetime


class ArtifactStore(Protocol):
    """아티팩트 저장소가 구현해야 할 인터페이스(프로토콜)입니다."""

    def init(self) -> None: ...

    def save(self, run_id: str, source_node: str, artifact_key: str, content: str) -> ArtifactRecord: ...

    def list(self, run_id: str | None = None) -> list[ArtifactRecord]: ...

    def latest(self, run_id: str, artifact_key: str | None = None) -> ArtifactRecord | None: ...

    def list_runs(self) -> list[str]: ...
