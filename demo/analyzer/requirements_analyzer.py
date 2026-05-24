from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

from analyzer.prompts import EXTRACT_PROMPT, REVIEW_PROMPT


ProgressCallback = Optional[Callable[[str], None]]


class RequirementsAnalyzer:
    def __init__(self, llm_client, model):
        self.llm_client = llm_client
        self.model = model

    def _notify(self, message: str, progress_callback: ProgressCallback = None) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def _build_system_prompt(self) -> str:
        return (
            "You are a precise requirements analysis assistant.\n"
            "Your job is to transform user input into a structured requirements JSON.\n"
            "Be conservative and source-faithful.\n"
            "Do not infer missing details unless they are explicitly stated in the source text.\n"
            "Prefer empty arrays or empty strings over plausible guesses.\n"
            "Do not add actor, inputs, expected results, entity descriptions, "
            "acceptance criteria, business rules, or constraints unless grounded in the text.\n"
            "Return only valid JSON."
        )

    def _call_llm(self, prompt: str) -> Dict[str, Any]:
        response = self.llm_client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": self._build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM 응답 content가 비어 있습니다.")

        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                "LLM이 유효한 JSON을 반환하지 않았습니다.\n"
                f"응답 내용:\n{content}"
            ) from e

    def extract_requirements(
        self,
        input_text: str,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        self._notify("요구사항 초안 추출 시작", progress_callback)
        started_at = time.time()

        prompt = EXTRACT_PROMPT.format(input_text=input_text)
        result = self._call_llm(prompt)

        elapsed = time.time() - started_at
        self._notify(f"요구사항 초안 추출 완료 ({elapsed:.2f}초)", progress_callback)

        return result

    def review_requirements(
        self,
        input_text: str,
        draft_json: Dict[str, Any],
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        self._notify("추출 결과 검토 시작", progress_callback)
        started_at = time.time()

        prompt = REVIEW_PROMPT.format(
            input_text=input_text,
            draft_json=json.dumps(draft_json, ensure_ascii=False, indent=2),
        )
        result = self._call_llm(prompt)

        elapsed = time.time() - started_at
        self._notify(f"추출 결과 검토 완료 ({elapsed:.2f}초)", progress_callback)

        return result

    def analyze(
        self,
        input_text: str,
        progress_callback: ProgressCallback = None,
        enable_review: bool = True,
    ) -> Dict[str, Any]:
        total_started_at = time.time()

        self._notify("입력 정리 중...", progress_callback)
        cleaned_input = input_text.strip()

        if not cleaned_input:
            raise ValueError("입력 텍스트가 비어 있습니다.")

        draft_result = self.extract_requirements(
            input_text=cleaned_input,
            progress_callback=progress_callback,
        )

        if enable_review:
            final_result = self.review_requirements(
                input_text=cleaned_input,
                draft_json=draft_result,
                progress_callback=progress_callback,
            )
        else:
            self._notify("검토 단계 생략", progress_callback)
            final_result = draft_result

        total_elapsed = time.time() - total_started_at
        self._notify(f"전체 분석 완료 ({total_elapsed:.2f}초)", progress_callback)

        return final_result