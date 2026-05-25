"""앱 진입점입니다.
멀티 에이전트 TDD 파이프라인을 초기화하고 실행하는 스크립트입니다.
"""

import argparse
from uuid import uuid4

from dotenv import load_dotenv
from core.checkpoint import get_latest_checkpoint_reference, resume_from_checkpoint
from core.db import get_latest_artifact, init_db, list_saved_artifacts, run_project
from core.logging import get_logger, setup_logging


logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""

    parser = argparse.ArgumentParser(description="Run or resume the multi-agent TDD pipeline.")
    parser.add_argument("--resume", action="store_true", dest="resume", help="Resume from the latest checkpoint.")
    parser.add_argument("--run-id", dest="run_id", help="Target run/thread ID to resume or reuse.")
    return parser.parse_args()


def main():
    """앱 진입 함수.

    환경변수를 로드하고 로깅을 설정한 뒤, 체크포인트 저장소를 초기화하고
    워크플로우를 실행합니다. 최종 상태 및 아티팩트를 로그로 출력합니다.
    """

    load_dotenv()
    setup_logging()
    logger.info("Initializing checkpoint store...")
    init_db()
    logger.info("Checkpoint store ready.")

    args = _parse_args()

    initial_state = {
        "functional_req": "사용자는 구글 소셜 로그인을 통해 사이트에 접속하고, 본인의 프로필 사진을 업로드할 수 있어야 한다.",
        "non_functional_req": "동시 접속자 1000명을 견딜 수 있어야 하며, 프로필 사진 업로드 용량은 5MB로 제한한다.",
    }

    if args.resume:
        latest_reference = get_latest_checkpoint_reference(args.run_id)
        if latest_reference is None:
            if args.run_id:
                logger.error("No checkpoint found to resume from for run_id=%s.", args.run_id)
            else:
                logger.error("No checkpoint found to resume from.")
            raise SystemExit(1)

        thread_id, checkpoint_id = latest_reference
        logger.info("Resuming multi-agent TDD pipeline from latest checkpoint: thread_id=%s checkpoint_id=%s", thread_id, checkpoint_id)
        thread_id, final_state = resume_from_checkpoint(thread_id, checkpoint_id)
    else:
        logger.info("Starting multi-agent TDD pipeline.")
        thread_id = args.run_id or uuid4().hex
        thread_id, final_state = run_project(initial_state, thread_id)

    logger.info("thread_id: %s", thread_id)
    logger.info("final_state_keys: %s", sorted(final_state.keys()))
    logger.info("artifact_count: %s", len(list_saved_artifacts(thread_id)))
    latest = get_latest_artifact(thread_id)
    if latest:
        logger.info("latest_artifact_key: %s", latest.artifact_key)

    logger.info("Pipeline complete. Use FastAPI to query checkpoints.")


if __name__ == "__main__":
    main()
