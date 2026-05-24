from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


NFRCategory = Literal[
    "security",
    "performance",
    "usability",
    "reliability",
    "availability",
    "maintainability",
    "compatibility",
    "other",
]

RequirementType = Literal["functional"]


class Requirement(BaseModel):
    id: str = Field(..., description="Unique requirement ID such as FR-001")
    type: RequirementType = Field(default="functional")
    actor: str = Field(default="")
    description: str = Field(default="")
    preconditions: List[str] = Field(default_factory=list)
    inputs: List[str] = Field(default_factory=list)
    expected_results: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class NonFunctionalRequirement(BaseModel):
    id: str = Field(..., description="Unique requirement ID such as NFR-001")
    category: NFRCategory = Field(default="other")
    description: str = Field(default="")


class Entity(BaseModel):
    name: str = Field(...)
    description: str = Field(default="")


class SRSOutput(BaseModel):
    requirements: List[Requirement] = Field(default_factory=list)
    non_functional_requirements: List[NonFunctionalRequirement] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)