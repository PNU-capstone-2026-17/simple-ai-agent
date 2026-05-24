import json
import time
from typing import Any, Callable, Dict, Optional

from .prompts import GENERATE_PROMPT


ProgressCallback = Optional[Callable[[str], None]]


class CodeGenerator:
    def __init__(self, llm_client, model: str):
        self.llm_client = llm_client
        self.model = model

    def _notify(self, message: str, progress_callback: ProgressCallback = None) -> None:
        if progress_callback:
            progress_callback(message)

    def _build_system_prompt(self) -> str:
        return (
            "You are a backend code generator. "
            "Return only valid JSON. "
            "Do not wrap output in markdown. "
            "Do not add explanations."
        )

    def _extract_text(self, response: Any) -> str:
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM 응답 content가 비어 있습니다.")
        return content.strip()

    def _strip_code_fences(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        elif text.startswith("```"):
            text = text[len("```"):].strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        return text

    def _chat_once(self, prompt: str, max_tokens: int = 2500) -> str:
        response = self.llm_client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": prompt},
            ],
        )
        return self._extract_text(response)

    def _repair_json_with_llm(self, broken_text: str) -> Dict[str, Any]:
        repair_prompt = f"""
The following text was intended to be JSON but is invalid.

Fix it so it becomes valid JSON.

Rules:
- Return only valid JSON.
- Do not use markdown fences.
- Preserve the original meaning.
- Do not add new features.
- The top-level result must be a JSON object.

Broken text:
{broken_text}
""".strip()

        repaired_text = self._chat_once(repair_prompt, max_tokens=2500)
        repaired_text = self._strip_code_fences(repaired_text)

        try:
            return json.loads(repaired_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "LLM이 유효한 JSON 복구에도 실패했습니다.\n"
                f"복구 응답 내용:\n{repaired_text}"
            ) from e

    def _call_llm_json(self, prompt: str, max_tokens: int = 2500) -> Dict[str, Any]:
        text = self._chat_once(prompt, max_tokens=max_tokens)
        text = self._strip_code_fences(text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = self._repair_json_with_llm(text)

        if not isinstance(data, dict):
            raise ValueError("LLM 응답 JSON의 최상위 구조가 객체(dict)가 아닙니다.")

        return data

    def generate(
        self,
        requirements_json: Dict[str, Any],
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        self._notify("코드 생성 시작", progress_callback)
        started_at = time.time()

        prompt = GENERATE_PROMPT.format(
            requirements_json=json.dumps(requirements_json, ensure_ascii=False, indent=2)
        )

        generated_files = self._call_llm_json(prompt, max_tokens=2500)

        required_files = {"app/main.py", "requirements.txt"}
        missing = required_files - set(generated_files.keys())
        if missing:
            raise ValueError(f"생성 결과에 필수 파일이 없습니다: {sorted(missing)}")

        for path, content in generated_files.items():
            if not isinstance(path, str):
                raise ValueError("생성 결과의 파일 경로 key는 문자열이어야 합니다.")
            if not isinstance(content, str):
                raise ValueError(f"파일 내용은 문자열이어야 합니다: {path}")

        elapsed = time.time() - started_at
        self._notify(f"코드 생성 완료 ({elapsed:.2f}초)", progress_callback)

        return {
            "implementation_plan": None,
            "generated_files": generated_files,
        }