# Simple AI Agent

간단한 멀티-에이전트 TDD 파이프라인과 단일 노드 실행기를 포함한 예제 프로젝트입니다.
이 저장소는 각 단계(요구분석, 시스템 설계, 개발, 테스트 커버리지)를 에이전트화하여
LLM을 활용한 산출물 생성과 검증 흐름을 시연합니다.

## 프로젝트 구조

- `main.py` - 전체 파이프라인을 간단히 실행하는 진입점
- `graph.py` - StateGraph 빌드 및 노드 라우팅 정의
- `api.py` - FastAPI 기반 아티팩트 조회/실행 API
- `agents/` - 개별 에이전트 모듈 및 프롬프트/스키마
- `core/` - 공통 유틸리티(LLM 호출, DB 어댑터, 로깅, 상태 타입 등)
- `scripts/run_single_node.py` - 단일 노드를 직접 실행하기 위한 헬퍼 스크립트
- `tests/sample_states/` - 단일 노드 실행에 사용할 샘플 입력 JSON
- `data/` - 로컬 checkpoint SQLite 데이터베이스(`checkpoints.sqlite3`) 등 런타임 아티팩트

## 요구사항(Prerequisites)

- Python 3.10+ 권장
- 의존성 설치:

```bash
pip install -r requirements.txt
```

## 환경 변수

- `AGENT_LLM_CONFIG_FILE` (선택): 에이전트별 LLM 설정 파일 경로 (기본: `agent_llm_config.json`)
- `LANGGRAPH_CHECKPOINT_DB_PATH` (선택): checkpoint SQLite 파일 경로 (기본: `data/checkpoints.sqlite3`)

LLM API 키/엔드포인트는 `agent_llm_config.json` 파일 내부에 설정하거나,
해당 파일에서 환경변수 참조(`${ENV_VAR}`)를 사용해 주입할 수 있습니다.

## 사용법

1) 단일 노드 실행 (디버그/개발용)

```bash
python scripts/run_single_node.py --node req_analysis --state tests/sample_states/req_analysis.json --out tests/outputs/req_analysis_out.json

python scripts/run_single_node.py --node dev --state tests/sample_states/dev_agent.json --out tests/outputs/dev_agent_out.json
```

`--node`로 지정할 수 있는 초기 버전의 노드: `req_analysis`, `dev`.

상태는 단계별 하위 객체로 관리됩니다. 예를 들어 요구사항 단계는 `requirements`,
시스템 설계 단계는 `system_design`, 개발 단계는 `development`, 커버리지 단계는 `coverage`
아래에 산출물과 `retry_count`, `is_passed`, `feedback`를 저장합니다.

2) 전체 파이프라인 실행

```bash
python main.py

python main.py --resume

python main.py --resume --run-id <run_id>
```

`main.py`는 예제 초기 상태를 생성하고 파이프라인을 실행한 뒤 결과와 아티팩트를 로그에 출력합니다.
`--resume`를 주면 저장된 checkpoint 중 가장 최근 checkpoint에서 이어서 실행합니다.
`--run-id`를 함께 주면 해당 run_id의 최신 checkpoint에서 재개합니다.

3) API로 실행/조회

```bash
uvicorn api:app --reload
```

서버가 기동되면 `/runs` 엔드포인트로 실행을 시작하거나,
`/runs/{run_id}/artifacts/latest` 등으로 아티펙트를 조회할 수 있습니다.

추가로 `/runs/{run_id}/checkpoints`에서 checkpoint 이력을 조회하고,
`/runs/{run_id}/resume`로 특정 checkpoint 또는 노드 기준 재실행을 시작할 수 있습니다.

4) 브라우저 기반 SSE 실행 콘솔

API 서버를 실행한 뒤 브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000/
```

- 프론트엔드 소스는 `frontend/` 디렉토리에 분리되어 있습니다.
- 화면에서 요구사항을 입력하고 `Start Stream`을 누르면 `/runs/stream` SSE 이벤트(`status`, `log`, `done`, `error`)를 실시간으로 확인할 수 있습니다.
- 완료 시 마지막 `run_id`가 화면에 표시되어 checkpoint/아티팩트 조회 API와 연계할 수 있습니다.

## 테스트 및 출력

- 샘플 입력은 `tests/sample_states/`에 있습니다.
- 실행 결과는 checkpoint SQLite와 `tests/outputs/` JSON에 저장됩니다.

## checkpoint 및 아티펙트

- 워크플로우 상태는 LangGraph checkpoint SQLite에 저장됩니다.
- 각 에이전트가 생성한 `req_spec`, `sys_diagram`, `source_code`, `test_coverage`, `current_tc`는 state에 포함되어 checkpoint history에서 다시 조회할 수 있습니다.
- `core.db`의 `list_saved_artifacts()`와 `get_latest_artifact()`는 checkpoint history를 읽어 아티펙트를 재구성합니다.
- `core/checkpoint.py`의 `resume_run()` 또는 `resume_from_checkpoint()` / `resume_from_node()` 헬퍼로 저장된 checkpoint에서 이어 실행할 수 있습니다.

## 비고

- LLM 호출 기능은 실제 API 키와 설정이 필요합니다. 테스트 환경에서는 `agent_llm_config.json`을
	적절히 구성하거나 모의(Mocking) 클라이언트를 사용하세요.
- 변경사항을 확인한 뒤 커밋/배포하시길 권장합니다.

## Minikube 배포 메모

Windows PowerShell에서 Minikube Docker 환경을 쓰려면 먼저 Minikube 프로필과 Docker 엔진이 정상 상태여야 합니다.

한 번에 실행하려면 아래 스크립트를 쓰면 됩니다. Docker Desktop이 먼저 실행 중이어야 합니다.

```powershell
.\scripts\deploy_minikube.ps1
```

스크립트가 내부에서 `minikube start`, Docker env 연결, 이미지 빌드, Secret 생성, Kubernetes 적용까지 처리합니다.

수동으로 실행하려면:

```powershell
minikube start
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
docker build -t simple-ai-agent:local .
```

`docker-env`만 단독으로 치면, Minikube 프로필이 아직 없을 때 바로 실패합니다.

- `minikube profile list`에서 `minikube` 프로필이 보여야 합니다.
- `docker build`가 `//./pipe/dockerDesktopLinuxEngine` 오류를 내면 Docker Desktop이 꺼져 있거나 엔진이 준비되지 않은 상태입니다.
- 민감한 환경변수는 `.env`를 직접 배포하지 말고 `kubectl create secret generic ... --from-env-file=.env`로 Secret을 만든 뒤 주입하세요.

