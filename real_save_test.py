import os
import pymysql
import operator
from typing import TypedDict, Optional, Annotated
from langgraph.graph import StateGraph, END
# from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.prompts import PromptTemplate
# from langchain_core.output_parsers import StrOutputParser

# ==========================================
# 0. 환경 설정 (API Key & DB)
# ==========================================
from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 환경변수 로드

os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "agent_project_db"),
    "charset": "utf8mb4"
}

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2)

# ==========================================
# 1. State 정의
# ==========================================
class ProjectState(TypedDict):
    functional_req: str
    non_functional_req: str
    
    req_spec: Optional[str]
    sys_diagram: Optional[str]
    source_code: Optional[str]
    test_coverage: Optional[str]
    
    current_tc: Optional[str]
    feedback: Optional[str]
    is_passed: bool
    retry_count: Annotated[int, operator.add]

# ==========================================
# 2. MySQL DB 헬퍼 함수 (실제 동작)
# ==========================================
def init_db():
    """데이터베이스와 테이블이 없으면 생성합니다."""
    # DB 자체 생성 (기존 DB가 없을 경우를 대비)
    temp_conn = pymysql.connect(host=DB_CONFIG["host"], user=DB_CONFIG["user"], password=DB_CONFIG["password"])
    with temp_conn.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} DEFAULT CHARACTER SET utf8mb4;")
    temp_conn.commit()
    temp_conn.close()

    # 테이블 생성
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_artifacts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phase_name VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()

def save_artifact_to_mysql(phase_name: str, content: str):
    """산출물을 MySQL에 실제로 INSERT 합니다."""
    if not content: return
    
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO project_artifacts (phase_name, content) VALUES (%s, %s)"
            cursor.execute(sql, (phase_name, content))
        conn.commit()
        print(f"   💾 [DB INSERT] '{phase_name}' 저장 완료!")
    except Exception as e:
        print(f"   ❌ [DB ERROR] {e}")
    finally:
        conn.close()

# ==========================================
# 3. LLM 프롬프트 헬퍼 함수
# ==========================================
def generate_with_llm(role_prompt: str, context: str, feedback: str = None) -> str:
    prompt_text = f"{role_prompt}\n\n[주어진 정보]\n{context}"
    if feedback and feedback != "Pass":
        prompt_text += f"\n\n[이전 테스트 실패 피드백 - 이를 반영하여 수정하세요]\n{feedback}"
        
    print("   [디버그] 🤖 구글 Gemini API 호출 중... (잠시만 기다려주세요)") # <- 추가
    response = llm.invoke(prompt_text).content
    print("   [디버그] ✅ Gemini 응답 완료!") # <- 추가
    return response

def evaluate_with_llm(target: str, test_cases: str) -> tuple[bool, str]:
    """LLM을 호출하여 산출물이 TC를 통과하는지 평가하는 공통 함수"""
    prompt = f"""
    당신은 엄격한 QA 엔지니어입니다. 아래의 [산출물]이 [테스트 케이스]를 모두 만족하는지 평가하세요.
    완벽하게 만족한다면 오직 'PASS' 라고만 출력하세요.
    부족한 점이 있다면 'FAIL: [구체적인 이유]' 형태로 출력하세요.

    [테스트 케이스]
    {test_cases}

    [산출물]
    {target}
    """
    response = llm.invoke(prompt).content.strip()
    if response.upper().startswith("PASS"):
        return True, "Pass"
    else:
        return False, response

# ==========================================
# 4. 에이전트 노드 정의 (실제 LLM 적용)
# ==========================================
# [Phase 1: Requirement]
def req_analysis_agent(state: ProjectState):
    print("   [디버그] ▶ 요구사항 분석 에이전트 진입함!") # <- 추가
    context = f"기능적 요구사항: {state['functional_req']}\n비기능적 요구사항: {state['non_functional_req']}"
    result = generate_with_llm("당신은 요구사항 분석가입니다. 마크다운 형식의 요구사항 명세서를 작성하세요.", context, state.get("feedback"))
    return {"req_spec": result, "retry_count": 1}

def req_tc_agent(state: ProjectState):
    result = generate_with_llm("당신은 QA 엔지니어입니다. 요구사항 명세서를 바탕으로 BDD(Given-When-Then) 형식의 테스트 케이스를 작성하세요.", state["req_spec"])
    return {"current_tc": result}

def req_testing_system(state: ProjectState):
    is_passed, feedback = evaluate_with_llm(state["req_spec"], state["current_tc"])
    return {"is_passed": is_passed, "feedback": feedback}

# [Phase 2: System Design]
def sys_design_agent(state: ProjectState):
    result = generate_with_llm("당신은 시스템 아키텍트입니다. 요구사항 명세서를 바탕으로 시스템 다이어그램과 아키텍처 설계를 텍스트로 자세히 작성하세요.", state["req_spec"], state.get("feedback"))
    return {"sys_diagram": result, "retry_count": 1}

def sys_tc_agent(state: ProjectState):
    result = generate_with_llm("당신은 아키텍처 테스터입니다. 시스템 설계도를 바탕으로 성능, 보안, 가용성 등에 대한 검증용 테스트 케이스를 작성하세요.", state["sys_diagram"])
    return {"current_tc": result}

def sys_testing_system(state: ProjectState):
    is_passed, feedback = evaluate_with_llm(state["sys_diagram"], state["current_tc"])
    return {"is_passed": is_passed, "feedback": feedback}

# [Phase 3: Development]
def dev_agent(state: ProjectState):
    result = generate_with_llm("당신은 시니어 개발자입니다. 시스템 설계를 바탕으로 파이썬 백엔드 소스 코드를 작성하세요.", state["sys_diagram"], state.get("feedback"))
    return {"source_code": result, "retry_count": 1}

def dev_tc_agent(state: ProjectState):
    result = generate_with_llm("당신은 테스트 엔지니어입니다. 주어진 코드를 검증할 수 있는 PyTest 기반의 유닛 테스트 코드를 작성하세요.", state["source_code"])
    return {"current_tc": result}

def dev_testing_system(state: ProjectState):
    is_passed, feedback = evaluate_with_llm(state["source_code"], state["current_tc"])
    return {"is_passed": is_passed, "feedback": feedback}

# [Phase 4: Coverage]
def test_agent(state: ProjectState):
    context = f"소스코드:\n{state['source_code']}\n\n유닛 테스트코드:\n{state['current_tc']}"
    result = generate_with_llm("당신은 코드 리뷰어입니다. 현재 테스트 커버리지 현황을 분석하고, 예외 처리가 누락된 부분을 찾아 커버리지 리포트를 작성하세요.", context, state.get("feedback"))
    return {"test_coverage": result, "retry_count": 1}

def coverage_tc_agent(state: ProjectState):
    result = generate_with_llm("당신은 통합 테스트 담당자입니다. 테스트 커버리지 리포트를 바탕으로 추가적인 통합 테스트 시나리오를 3개 작성하세요.", state["test_coverage"])
    return {"current_tc": result}

def coverage_testing_system(state: ProjectState):
    is_passed, feedback = evaluate_with_llm(state["test_coverage"], state["current_tc"])
    return {"is_passed": is_passed, "feedback": feedback}

# ==========================================
# 5. DB 저장 전용 노드
# ==========================================
def save_req_db_node(state: ProjectState):
    save_artifact_to_mysql("REQUIREMENT_SPEC", state["req_spec"])
    return {"feedback": "Pass"} # 다음 페이즈로 넘어가므로 피드백 초기화

def save_sys_db_node(state: ProjectState):
    save_artifact_to_mysql("SYSTEM_DIAGRAM", state["sys_diagram"])
    return {"feedback": "Pass"}

def save_dev_db_node(state: ProjectState):
    save_artifact_to_mysql("SOURCE_CODE", state["source_code"])
    return {"feedback": "Pass"}

def save_coverage_db_node(state: ProjectState):
    save_artifact_to_mysql("TEST_COVERAGE", state["test_coverage"])
    return {"feedback": "Pass"}

# ==========================================
# 6. 라우팅 함수
# ==========================================
MAX_RETRIES = 3  # 최대 재시도 횟수 제한

def route_req(state: ProjectState):
    if state["is_passed"]:
        return "save_req_db_node"
    if state["retry_count"] >= MAX_RETRIES:
        print("🚨 [경고] 최대 재시도 횟수 초과로 프로세스를 중단합니다.")
        return END
    return "req_analysis_agent"

def route_sys(state: ProjectState):
    if state["is_passed"]:
        return "save_sys_db_node"
    if state["retry_count"] >= MAX_RETRIES:
        print("🚨 [경고] 최대 재시도 횟수 초과로 프로세스를 중단합니다.")
        return END
    return "sys_design_agent"

def route_dev(state: ProjectState):
    if state["is_passed"]:
        return "save_dev_db_node"
    if state["retry_count"] >= MAX_RETRIES:
        print("🚨 [경고] 최대 재시도 횟수 초과로 프로세스를 중단합니다.")
        return END
    return "dev_agent"

def route_coverage(state: ProjectState):
    if state["is_passed"]:
        return "save_coverage_db_node"
    if state["retry_count"] >= MAX_RETRIES:
        print("🚨 [경고] 최대 재시도 횟수 초과로 프로세스를 중단합니다.")
        return END
    return "test_agent"

# ==========================================
# 7. 그래프 조립
# ==========================================
workflow = StateGraph(ProjectState)

workflow.add_node("req_analysis_agent", req_analysis_agent)
workflow.add_node("req_tc_agent", req_tc_agent)
workflow.add_node("req_testing_system", req_testing_system)
workflow.add_node("save_req_db_node", save_req_db_node)

workflow.add_node("sys_design_agent", sys_design_agent)
workflow.add_node("sys_tc_agent", sys_tc_agent)
workflow.add_node("sys_testing_system", sys_testing_system)
workflow.add_node("save_sys_db_node", save_sys_db_node)

workflow.add_node("dev_agent", dev_agent)
workflow.add_node("dev_tc_agent", dev_tc_agent)
workflow.add_node("dev_testing_system", dev_testing_system)
workflow.add_node("save_dev_db_node", save_dev_db_node)

workflow.add_node("test_agent", test_agent)
workflow.add_node("coverage_tc_agent", coverage_tc_agent)
workflow.add_node("coverage_testing_system", coverage_testing_system)
workflow.add_node("save_coverage_db_node", save_coverage_db_node)

workflow.set_entry_point("req_analysis_agent")

workflow.add_edge("req_analysis_agent", "req_tc_agent")
workflow.add_edge("req_tc_agent", "req_testing_system")
workflow.add_conditional_edges("req_testing_system", route_req)
workflow.add_edge("save_req_db_node", "sys_design_agent")

workflow.add_edge("sys_design_agent", "sys_tc_agent")
workflow.add_edge("sys_tc_agent", "sys_testing_system")
workflow.add_conditional_edges("sys_testing_system", route_sys)
workflow.add_edge("save_sys_db_node", "dev_agent")

workflow.add_edge("dev_agent", "dev_tc_agent")
workflow.add_edge("dev_tc_agent", "dev_testing_system")
workflow.add_conditional_edges("dev_testing_system", route_dev)
workflow.add_edge("save_dev_db_node", "test_agent")

workflow.add_edge("test_agent", "coverage_tc_agent")
workflow.add_edge("coverage_tc_agent", "coverage_testing_system")
workflow.add_conditional_edges("coverage_testing_system", route_coverage)
workflow.add_edge("save_coverage_db_node", END)

app = workflow.compile()

# ==========================================
# 8. 실행부
# ==========================================
if __name__ == "__main__":
    # 1. DB 초기화 (테이블 생성)
    print("⚙️ 데이터베이스 초기화 중...")
    init_db()
    print("✅ 데이터베이스 준비 완료.\n")

    # 2. 사용자 입력
    initial_state = {
        "functional_req": "사용자는 구글 소셜 로그인을 통해 사이트에 접속하고, 본인의 프로필 사진을 업로드할 수 있어야 한다.",
        "non_functional_req": "동시 접속자 1000명을 견딜 수 있어야 하며, 프로필 사진 업로드 용량은 5MB로 제한한다.",
        "retry_count": 0
    }

    print("🚀 멀티 에이전트 TDD 파이프라인 시작...\n")
    
    # 그래프 실행 및 스트리밍 로그 출력
    for output in app.stream(initial_state): # invoke는 전체 결과를 기다려야 하지만, stream은 각 노드가 완료될 때마다 결과를 출력한다
        for node_name, state_update in output.items():
            print(f"▶ [완료된 작업]: {node_name}")
            
            # 테스트 시스템에서 피드백이 발생한 경우 출력
            if node_name.endswith("_testing_system"):
                if state_update.get("is_passed"):
                    print("   [결과] ✅ 테스트 통과!")
                else:
                    print(f"   [결과] ❌ 테스트 실패. 피드백: {state_update.get('feedback')}")
                    print("   🔄 산출물 갱신을 위해 이전 단계로 돌아갑니다.")
                    
            print("-" * 50)
            
    print("\n✨ 모든 파이프라인이 정상 종료되었습니다. MySQL DB를 확인해보세요!")