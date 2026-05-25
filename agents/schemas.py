"""에이전트 간에 교환되는 JSON 스키마(Pydantic 모델)를 정의합니다.
요구사항, 테스트 케이스, 설계, 개발 출력 등 각종 스키마를 포함합니다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RequirementItem(BaseModel):
    id: str = Field(..., min_length=1)
    requirement: str = Field(..., min_length=1)


class ReqAnalysisOutput(BaseModel):
    functional_requirements: list[RequirementItem] = Field(..., min_length=1)
    non_functional_requirements: list[RequirementItem] = Field(..., min_length=1)


class BddTestCase(BaseModel):
    title: str = Field(..., min_length=1)
    given: str = Field(..., min_length=1)
    when: str = Field(..., min_length=1)
    then: str = Field(..., min_length=1)


class PyTestCase(BaseModel):
    title: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class ReqTcOutput(BaseModel):
    test_cases: list[BddTestCase] = Field(..., min_length=1)


class SysDesignOutput(BaseModel):
    sys_diagram: str = Field(..., min_length=1)


class SysTcOutput(BaseModel):
    test_cases: list[BddTestCase] = Field(..., min_length=1)


class DevOutput(BaseModel):
    source_code: str = Field(..., min_length=1)


class DevTcOutput(BaseModel):
    test_cases: list[PyTestCase] = Field(..., min_length=1)


class CoverageOutput(BaseModel):
    test_coverage: str = Field(..., min_length=1)


class CoverageTcOutput(BaseModel):
    test_cases: list[BddTestCase] = Field(..., min_length=1)