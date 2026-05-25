"""단일 노드(에이전트)를 직접 실행하기 위한 스크립트입니다.
테스트 목적으로 JSON 상태 파일을 읽어 특정 노드를 실행하고 결과를 출력합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph import invoke_single_node
from core.state import ProjectState, normalize_project_state


def load_state(path: Path) -> ProjectState:
    """JSON 파일에서 상태를 읽고 `ProjectState`로 변환해 반환합니다.

    필수 키가 없으면 `ValueError`를 발생시킵니다.
    """

    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("State file must contain a JSON object.")

    required_keys = ("functional_req", "non_functional_req", "run_id")
    missing_keys = [key for key in required_keys if key not in payload]
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise ValueError(f"Missing required state keys: {missing}")

    return normalize_project_state(cast(dict[str, Any], payload))


def main() -> int:
    """스크립트 진입점: 단일 노드를 직접 실행하고 결과를 표준 출력과 파일에 씁니다."""

    load_dotenv()
    parser = argparse.ArgumentParser(description="Run one agent node directly for testing.")
    parser.add_argument("--node", required=True, help="Single node name, e.g. req_analysis or dev")
    parser.add_argument("--state", required=True, help="Path to a JSON file with the node input state")
    parser.add_argument("--out", help="Optional path to write the resulting JSON")
    args = parser.parse_args()

    state: ProjectState = load_state(Path(args.state))
    result = invoke_single_node(args.node, state)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)

    print(rendered)

    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())