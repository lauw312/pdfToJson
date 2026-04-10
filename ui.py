from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from core import DEFAULT_USER_PROMPT


HIDDEN_DETAIL_COLUMNS = {"INSP_DTL_ID", "INSP_ID"}


def main_to_editor_rows(main_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": key, "value": value} for key, value in main_data.items()]


def editor_rows_to_main(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        key = str(row.get("field", "")).strip()
        if key:
            result[key] = row.get("value")
    return result


def sanitize_detail_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        normalized = {str(key).strip(): value for key, value in row.items() if str(key).strip()}
        if any(value not in ("", None) for value in normalized.values()):
            cleaned.append(normalized)
    return cleaned


def start_edit_session() -> None:
    result = st.session_state.get("last_result", {})
    st.session_state["edit_main_draft"] = main_to_editor_rows(result.get("main", {}))
    st.session_state["edit_detail_draft"] = [dict(row) for row in result.get("detail", [])]
    st.session_state["detail_visible_columns"] = [
        column
        for column in pd.DataFrame(result.get("detail", [])).columns
        if column not in HIDDEN_DETAIL_COLUMNS
    ]


def clear_edit_session() -> None:
    session_keys = [
        "edit_main_draft",
        "edit_detail_draft",
        "detail_visible_columns",
        "main_editor_dialog",
        "detail_editor_dialog",
    ]
    for key in session_keys:
        st.session_state.pop(key, None)


def init_session_state() -> None:
    defaults = {
        "edit_mode": False,
        "is_extracting": False,
        "uploaded_file_hash": "",
        "pdf_bytes": b"",
        "pdf_text": "",
        "pdf_tables": [],
        "save_feedback": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_sidebar_settings() -> tuple[str, str, bool, str, str]:
    with st.sidebar:
        st.header("LLM Settings")
        endpoint_url = st.text_input("Endpoint URL", value="http://ai.paruda.com:11434/api/chat")
        model = st.text_input("Model", value="gemma4:e4b")
        api_key_required = st.toggle("Require API Key", value=False)
        api_key = ""
        if api_key_required:
            api_key = st.text_input("API Key", type="password", placeholder="Bearer token")
        extra_prompt = st.text_area(
            "Extra Prompt",
            value=DEFAULT_USER_PROMPT,
            height=420,
            help="Additional instructions appended to the extraction request.",
        )

    return endpoint_url, model, api_key_required, api_key, extra_prompt


def render_main_section(main_data: Any) -> None:
    st.subheader("Main")
    if isinstance(main_data, dict):
        table_rows = [{"field": key, "value": value} for key, value in main_data.items()]
        if table_rows:
            st.dataframe(table_rows, use_container_width=True, hide_index=True)
        with st.expander("Main JSON", expanded=False):
            st.code(json.dumps(main_data, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("The main value is not an object.")
        st.write(main_data)


def render_detail_section(detail_data: Any) -> None:
    st.subheader("Detail")
    if isinstance(detail_data, list):
        if detail_data:
            st.dataframe(detail_data, use_container_width=True, hide_index=True)
        with st.expander("Detail JSON", expanded=False):
            st.code(json.dumps(detail_data, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("The detail value is not an array.")
        st.write(detail_data)


def render_extracted_tables(tables: list[dict[str, Any]]) -> None:
    st.subheader("Extracted Tables")
    if not tables:
        st.info("No tables were detected. Only extracted text will be sent to the LLM.")
        return

    for table in tables:
        st.markdown(f"Page {table['page']} / Table {table['table_index']}")
        st.dataframe(table["rows"], use_container_width=True)


@st.dialog("Edit Mapping", width="large")
def render_edit_dialog() -> None:
    main_rows = st.session_state.get("edit_main_draft")
    detail_rows = st.session_state.get("edit_detail_draft")
    if main_rows is None or detail_rows is None:
        start_edit_session()
        main_rows = st.session_state.get("edit_main_draft", [])
        detail_rows = st.session_state.get("edit_detail_draft", [])

    st.markdown("Main")
    edited_main_df = st.data_editor(
        pd.DataFrame(main_rows),
        use_container_width=True,
        num_rows="dynamic",
        key="main_editor_dialog",
    )
    st.session_state["edit_main_draft"] = edited_main_df.to_dict(orient="records")

    st.markdown("Detail")
    detail_df = pd.DataFrame(detail_rows)
    detail_columns = [column for column in detail_df.columns if column not in HIDDEN_DETAIL_COLUMNS]
    if not detail_df.empty and HIDDEN_DETAIL_COLUMNS:
        detail_df = detail_df[[column for column in detail_df.columns if column not in HIDDEN_DETAIL_COLUMNS]]

    if detail_columns:
        if "detail_visible_columns" not in st.session_state or not st.session_state["detail_visible_columns"]:
            st.session_state["detail_visible_columns"] = detail_columns[:]
        selected_visible_columns = st.multiselect(
            "Visible Detail Columns",
            options=detail_columns,
            default=st.session_state.get("detail_visible_columns", detail_columns),
            key="detail_visible_columns",
            help="Hidden columns are excluded only from the current editor view.",
        )
        detail_df = pd.DataFrame(
            [
                {key: value for key, value in row.items() if key in selected_visible_columns}
                for row in st.session_state.get("edit_detail_draft", [])
            ]
        )

    edited_detail_df = st.data_editor(
        detail_df,
        use_container_width=True,
        num_rows="dynamic",
        key="detail_editor_dialog",
    )
    st.session_state["edit_detail_draft"] = edited_detail_df.to_dict(orient="records")

    updated_result = {
        "main": editor_rows_to_main(st.session_state.get("edit_main_draft", [])),
        "detail": sanitize_detail_rows(st.session_state.get("edit_detail_draft", [])),
    }

    save_col, download_col, cancel_col = st.columns(3)
    with save_col:
        if st.button("Save", type="primary", use_container_width=True):
            st.session_state["last_result"] = updated_result
            st.session_state["edit_mode"] = False
            clear_edit_session()
            st.session_state["save_feedback"] = {
                "type": "success",
                "message": "Saved mapping changes.",
            }
            st.rerun()
    with download_col:
        st.download_button(
            "Download JSON",
            data=json.dumps(updated_result, ensure_ascii=False, indent=2),
            file_name="matched_result.json",
            mime="application/json",
            use_container_width=True,
        )
    with cancel_col:
        if st.button("Cancel", use_container_width=True):
            st.session_state["edit_mode"] = False
            clear_edit_session()
            st.rerun()
