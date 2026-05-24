from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from analyzer.schemas import SRSOutput


def strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_first_json_object(text: str) -> str:
    text = strip_code_fences(text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model output.")

    return text[start:end + 1]


def parse_llm_json(text: str) -> Dict[str, Any]:
    raw = extract_first_json_object(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse model output as JSON: {e}") from e


def _normalize_string_list(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []

    result = []
    for item in items:
        if item is None:
            continue
        value = str(item).strip()
        if value:
            result.append(value)
    return result


def _normalize_requirements(data: Dict[str, Any]) -> None:
    requirements = data.get("requirements")
    if not isinstance(requirements, list):
        data["requirements"] = []
        return

    normalized = []
    for req in requirements:
        if not isinstance(req, dict):
            continue

        description = str(req.get("description", "")).strip()
        if not description:
            continue

        normalized.append({
            "id": str(req.get("id", "")).strip(),
            "type": "functional",
            "actor": str(req.get("actor", "")).strip(),
            "description": description,
            "preconditions": _normalize_string_list(req.get("preconditions", [])),
            "inputs": _normalize_string_list(req.get("inputs", [])),
            "expected_results": _normalize_string_list(req.get("expected_results", [])),
            "acceptance_criteria": _normalize_string_list(req.get("acceptance_criteria", [])),
        })

    data["requirements"] = normalized


def _normalize_nfrs(data: Dict[str, Any]) -> None:
    nfrs = data.get("non_functional_requirements")
    if not isinstance(nfrs, list):
        data["non_functional_requirements"] = []
        return

    allowed = {
        "security",
        "performance",
        "usability",
        "reliability",
        "availability",
        "maintainability",
        "compatibility",
        "other",
    }

    normalized = []
    for nfr in nfrs:
        if not isinstance(nfr, dict):
            continue

        description = str(nfr.get("description", "")).strip()
        if not description:
            continue

        category = str(nfr.get("category", "other")).strip().lower()
        if category not in allowed:
            category = "other"

        normalized.append({
            "id": str(nfr.get("id", "")).strip(),
            "category": category,
            "description": description,
        })

    data["non_functional_requirements"] = normalized


def _normalize_entities(data: Dict[str, Any]) -> None:
    entities = data.get("entities")
    if not isinstance(entities, list):
        data["entities"] = []
        return

    normalized = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue

        name = str(entity.get("name", "")).strip()
        description = str(entity.get("description", "")).strip()

        if name:
            normalized.append({
                "name": name,
                "description": description,
            })

    data["entities"] = normalized


def _normalize_top_level_lists(data: Dict[str, Any]) -> None:
    data["business_rules"] = _normalize_string_list(data.get("business_rules", []))
    data["constraints"] = _normalize_string_list(data.get("constraints", []))


def _dedupe_string_list(items: List[str]) -> List[str]:
    seen = set()
    result = []

    for item in items:
        key = re.sub(r"\s+", " ", item.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item.strip())

    return result


def _dedupe_requirements(requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for req in requirements:
        key = (
            req.get("actor", "").strip().lower(),
            re.sub(r"\s+", " ", req.get("description", "").strip().lower()),
        )
        if key in seen:
            continue
        seen.add(key)

        req["preconditions"] = _dedupe_string_list(req.get("preconditions", []))
        req["inputs"] = _dedupe_string_list(req.get("inputs", []))
        req["expected_results"] = _dedupe_string_list(req.get("expected_results", []))
        req["acceptance_criteria"] = _dedupe_string_list(req.get("acceptance_criteria", []))
        result.append(req)

    return result


def _dedupe_nfrs(nfrs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for nfr in nfrs:
        key = (
            nfr.get("category", "").strip().lower(),
            re.sub(r"\s+", " ", nfr.get("description", "").strip().lower()),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(nfr)

    return result


def _dedupe_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for entity in entities:
        key = entity["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(entity)

    return result


def _reassign_ids(data: Dict[str, Any]) -> None:
    for idx, req in enumerate(data["requirements"], start=1):
        req["id"] = f"FR-{idx:03d}"

    for idx, nfr in enumerate(data["non_functional_requirements"], start=1):
        nfr["id"] = f"NFR-{idx:03d}"


def normalize_srs_json(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Parsed JSON must be an object.")

    normalized = dict(data)

    _normalize_requirements(normalized)
    _normalize_nfrs(normalized)
    _normalize_entities(normalized)
    _normalize_top_level_lists(normalized)

    normalized["requirements"] = _dedupe_requirements(normalized["requirements"])
    normalized["non_functional_requirements"] = _dedupe_nfrs(normalized["non_functional_requirements"])
    normalized["entities"] = _dedupe_entities(normalized["entities"])
    normalized["business_rules"] = _dedupe_string_list(normalized["business_rules"])
    normalized["constraints"] = _dedupe_string_list(normalized["constraints"])

    _reassign_ids(normalized)

    return normalized


def parse_normalize_validate(text: str) -> Dict[str, Any]:
    parsed = parse_llm_json(text)
    normalized = normalize_srs_json(parsed)
    validated = SRSOutput.model_validate(normalized)
    return validated.model_dump()