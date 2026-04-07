from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pdfplumber
import streamlit as st
from pypdf import PdfReader


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
    if any(keyword in " ".join(first) for keyword in ["검사", "항목", "단위", "기준", "결과", "판정"]):
        return [cell or f"col_{index + 1}" for index, cell in enumerate(first)], rows[1:]

    width = max(len(row) for row in rows)
    return [f"col_{index + 1}" for index in range(width)], rows


def standardize_header_name(name: str) -> str:
    compact = re.sub(r"\s+", "", name)
    mapping = {
        "검사항목": "inspection_item",
        "시험항목": "inspection_item",
        "항목": "inspection_item",
        "단위": "unit",
        "기준": "criteria",
        "결과": "result",
        "항목판정": "judgment",
        "판정": "judgment",
        "시험방법": "test_method",
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
