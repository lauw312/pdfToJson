from __future__ import annotations

import json
from typing import Any

import requests

from prompts import DEFAULT_USER_PROMPT, SYSTEM_PROMPT, TABLE_GUIDE


def build_llm_source_payload(pdf_text: str, tables: list[dict[str, Any]]) -> str:
    payload = {
        "table_extraction_priority": True,
        "tables": tables,
        "raw_text": pdf_text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_user_prompt(pdf_text: str, tables: list[dict[str, Any]], extra_prompt: str) -> str:
    return f"""
추가 사용자 지시:
{extra_prompt.strip() or DEFAULT_USER_PROMPT}

표 해석 추가 지시:
{TABLE_GUIDE}

PDF 구조화 입력(JSON):
{build_llm_source_payload(pdf_text, tables)}
""".strip()


def normalize_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def request_json_from_llm(
    *,
    api_key: str,
    api_key_required: bool,
    endpoint_url: str,
    model: str,
    pdf_text: str,
    tables: list[dict[str, Any]],
    extra_prompt: str,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key_required and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(pdf_text, tables, extra_prompt)},
        ],
        "options": {"temperature": 0.2},
    }

    response = requests.post(endpoint_url, headers=headers, json=payload, timeout=180)
    response.raise_for_status()
    response_json = response.json()

    raw_text = normalize_json_text(
        response_json.get("message", {}).get("content", "")
        or response_json.get("response", "")
        or ""
    )
    if not raw_text:
        raise ValueError("LLM 응답이 비어 있습니다.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM이 유효한 JSON을 반환하지 않았습니다: {raw_text}") from exc

    if not isinstance(data, dict):
        raise ValueError("최상위 응답은 JSON 객체여야 합니다.")
    if "main" not in data or "detail" not in data:
        raise ValueError('응답에는 "main" 과 "detail" 키가 모두 필요합니다.')
    return data
