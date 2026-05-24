import json

from file_writer import write_generated_files
from graph import build_graph


def main():
    graph = build_graph()

    user_input = """
    사용자는 이메일과 비밀번호로 회원가입할 수 있어야 한다.
    사용자는 로그인할 수 있어야 한다.
    로그인 실패 시 에러 메시지를 보여줘야 한다.
    관리자는 사용자 목록을 조회할 수 있어야 한다.
    비밀번호는 안전하게 저장되어야 한다.
    """

    result = graph.invoke({
        "raw_input": user_input
    })

    if result.get("error"):
        print("에러 발생:")
        print(result["error"])
        return

    print("=== requirements ===")
    print(json.dumps(result.get("requirements", {}), ensure_ascii=False, indent=2))

    print("\n=== codegen_result ===")
    print(json.dumps(result.get("codegen_result", {}), ensure_ascii=False, indent=2))

    generated_files = result["codegen_result"]["generated_files"]
    
    write_generated_files("output_backend", generated_files)

    print("\n생성된 파일이 generated_project 폴더에 저장되었습니다.")

if __name__ == "__main__":
    main()