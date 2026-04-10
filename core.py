from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import pdfplumber
import requests
import streamlit as st
from pypdf import PdfReader


SYSTEM_PROMPT = """
You are a data analyst specialized in reading PDF documents and extracting structured JSON.

Your job:
1. Read the provided PDF text.
2. Infer the most important fields even if some values are ambiguous.
3. Return only valid JSON.
4. The JSON root must contain exactly two keys: "main" and "detail".

Output rules:
- "main" must be an object containing concise high-level fields.
- "detail" must be an array of detailed extracted or inferred items.
- Each item in "detail" should include:
  - "category"
  - "field"
  - "value"
  - "confidence" ("high", "medium", or "low")
  - "evidence"
- If a value is missing, use null.
- If a value is inferred, keep the best estimate and lower confidence.
- Do not add markdown fences.
- Return JSON only.
""".strip()


DEFAULT_USER_PROMPT = Path(__file__).resolve().with_name("default_user_prompt.md").read_text(encoding="utf-8").strip()


TABLE_GUIDE = """
?쒓? ?덉쑝硫??띿뒪?몃낫????援ъ“瑜??곗꽑 ?댁꽍?댁쨾.
?뱁엳 ?꾨옒 洹쒖튃??吏耳쒖쨾.
1. 而щ읆 ?ㅻ뜑媛 蹂댁씠硫??ㅻ뜑 湲곗??쇰줈 媛?? 媛믪쓣 留ㅼ묶?쒕떎.
2. 蹂묓빀?濡??명빐 鍮?移몄씠 ?덉쑝硫?諛붾줈 ?????먮뒗 媛숈? 洹몃９??媛믪쓣 ?댁뼱諛쏆븘 ?댁꽍?쒕떎.
3. 寃?ы몴 ?뺥깭?쇰㈃ 寃?ы빆紐? ?⑥쐞, 湲곗?, 寃곌낵, ??ぉ?먯젙???곗꽑?곸쑝濡?遺꾨━?쒕떎.
4. ?먯젙, ?쒗뿕諛⑸쾿 媛숈? ?붿빟 ?됱? main?먮룄 諛섏쁺?쒕떎.
5. detail?먮뒗 ?쒖쓽 媛??됱쓣 媛?ν븳 ???먮옒 ? 湲곗??쇰줈 蹂댁〈?쒕떎.
""".strip()


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages: list[str] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        cleaned = text.strip()
        if cleaned:
            pages.append(f"[Page {index}]\n{cleaned}")

    return "\n\n".join(pages).strip()


@st.cache_data(show_spinner=False)
def extract_pdf_text_cached(file_bytes: bytes) -> str:
    return extract_pdf_text(file_bytes)


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def normalize_row_length(row: list[str], width: int) -> list[str]:
    values = row[:width]
    if len(values) < width:
        values.extend([""] * (width - len(values)))
    return values


def fill_merged_cells(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return rows

    filled: list[list[str]] = [rows[0][:]]
    for row in rows[1:]:
        prev = filled[-1]
        current = row[:]
        for index, value in enumerate(current):
            if not value and index < len(prev):
                current[index] = prev[index]
        filled.append(current)
    return filled


def choose_header(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    default_header = ["col_1", "col_2", "col_3", "col_4", "col_5"]
    if not rows:
        return default_header, []

    first = rows[0]
    if any(keyword in " ".join(first) for keyword in ["寃??", "??ぉ", "?⑥쐞", "湲곗?", "寃곌낵", "?먯젙"]):
        return [cell or f"col_{index + 1}" for index, cell in enumerate(first)], rows[1:]

    width = max(len(row) for row in rows)
    return [f"col_{index + 1}" for index in range(width)], rows


def standardize_header_name(name: str) -> str:
    compact = re.sub(r"\s+", "", name)
    mapping = {
        "寃?ы빆紐?": "inspection_item",
        "?쒗뿕??ぉ": "inspection_item",
        "??ぉ": "inspection_item",
        "?⑥쐞": "unit",
        "湲곗?": "criteria",
        "寃곌낵": "result",
        "??ぉ?먯젙": "judgment",
        "?먯젙": "judgment",
        "?쒗뿕諛⑸쾿": "test_method",
    }
    return mapping.get(compact, compact or "value")


def extract_pdf_tables(file_bytes: bytes) -> list[dict[str, Any]]:
    extracted_tables: list[dict[str, Any]] = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_tolerance": 5,
        "snap_tolerance": 3,
        "join_tolerance": 3,
    }

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_tables = page.extract_tables(table_settings=table_settings) or []
            for table_index, table in enumerate(raw_tables, start=1):
                cleaned_rows = []
                for raw_row in table:
                    cells = [clean_cell(cell) for cell in (raw_row or [])]
                    if any(cells):
                        cleaned_rows.append(cells)

                if not cleaned_rows:
                    continue

                width = max(len(row) for row in cleaned_rows)
                normalized_rows = [normalize_row_length(row, width) for row in cleaned_rows]
                header, body_rows = choose_header(normalized_rows)
                body_rows = fill_merged_cells(body_rows)

                records: list[dict[str, str]] = []
                for row in body_rows:
                    record: dict[str, str] = {}
                    for index, value in enumerate(row):
                        key = header[index] if index < len(header) else f"col_{index + 1}"
                        record[standardize_header_name(key)] = value
                    if any(record.values()):
                        records.append(record)

                if records:
                    extracted_tables.append(
                        {
                            "page": page_number,
                            "table_index": table_index,
                            "header": header,
                            "rows": records,
                        }
                    )

    return extracted_tables


@st.cache_data(show_spinner=False)
def extract_pdf_tables_cached(file_bytes: bytes) -> list[dict[str, Any]]:
    return extract_pdf_tables(file_bytes)


def build_llm_source_payload(pdf_text: str, tables: list[dict[str, Any]]) -> str:
    payload = {
        "table_extraction_priority": True,
        "tables": tables,
        "raw_text": pdf_text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_user_prompt(pdf_text: str, tables: list[dict[str, Any]], extra_prompt: str) -> str:
    return f"""
異붽? ?ъ슜??吏??
{extra_prompt.strip() or DEFAULT_USER_PROMPT}

???댁꽍 異붽? 吏??
{TABLE_GUIDE}

PDF 援ъ“???낅젰(JSON):
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
        raise ValueError("LLM ?묐떟??鍮꾩뼱 ?덉뒿?덈떎.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM???좏슚??JSON??諛섑솚?섏? ?딆븯?듬땲?? {raw_text}") from exc

    if not isinstance(data, dict):
        raise ValueError("理쒖긽???묐떟? JSON 媛앹껜?ъ빞 ?⑸땲??")
    if "main" not in data or "detail" not in data:
        raise ValueError('?묐떟?먮뒗 "main" 怨?"detail" ?ㅺ? 紐⑤몢 ?꾩슂?⑸땲??')
    return data
