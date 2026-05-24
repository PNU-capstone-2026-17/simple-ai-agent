import os
from dotenv import load_dotenv
from datetime import datetime

from typing import TypedDict, Dict, Any

from langgraph.graph import StateGraph, START, END
from openai import OpenAI

from analyzer.requirements_analyzer import RequirementsAnalyzer
from codegen.code_generator import CodeGenerator

load_dotenv()


def console_progress(message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}")


class AgentState(TypedDict, total=False):
    raw_input: str
    requirements: Dict[str, Any]
    codegen_result: Dict[str, Any]
    error: str

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL")

def create_nvidia_client() -> OpenAI:
    if not NVIDIA_API_KEY:
        raise ValueError("NVIDIA_API_KEY is not set in environment variables.")

    return OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        timeout=60.0,
    )

CF_BASE_URL = os.getenv("CF_BASE_URL")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")

def create_cloudflare_client() -> OpenAI:
    if not CF_API_TOKEN:
        raise ValueError("CF_API_TOKEN is not set in environment variables.")
    
    return OpenAI(
        base_url=CF_BASE_URL,
        api_key=CF_API_TOKEN,
        timeout=60.0,
    )


#analyzer = RequirementsAnalyzer(
#    llm_client=create_nvidia_client(),
#    model="minimaxai/minimax-m2.7",
#)

code_generator = CodeGenerator(
    llm_client=create_nvidia_client(),
    model="qwen/qwen3-coder-480b-a35b-instruct",
)

analyzer = RequirementsAnalyzer(
    llm_client=create_cloudflare_client(),
    model="@cf/meta/llama-3.1-70b-instruct-fp8-fast",
)

#code_generator = CodeGenerator(
#    llm_client=create_cloudflare_client(),
#    model="@cf/qwen/qwen2.5-coder-32b-instruct",
#)


def analyze_requirements_node(state: AgentState) -> AgentState:
    try:
        raw_input = state.get("raw_input", "").strip()
        if not raw_input:
            return {
                **state,
                "error": "raw_input이 비어 있습니다."
            }

        result = analyzer.analyze(raw_input,
        progress_callback=console_progress,
        enable_review=False,)
        return {
            **state,
            "requirements": result,
        }
    except Exception as e:
        return {
            **state,
            "error": f"requirements analysis failed: {str(e)}"
        }


def generate_code_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    try:
        requirements = state.get("requirements", {})
        if not requirements:
            return {
                **state,
                "error": "requirements가 비어 있습니다."
            }

        result = code_generator.generate(requirements,
        progress_callback=console_progress, )

        return {
            **state,
            "codegen_result": result,
        }
    except Exception as e:
        return {
            **state,
            "error": f"code generation failed: {str(e)}"
        }


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("analyze_requirements", analyze_requirements_node)
    builder.add_node("generate_code", generate_code_node)

    builder.add_edge(START, "analyze_requirements")
    builder.add_edge("analyze_requirements", "generate_code")
    builder.add_edge("generate_code", END)

    return builder.compile()