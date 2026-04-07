from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import streamlit as st

from db_utils import DEFAULT_DB_CONFIG, delete_db_profile, load_db_profiles, normalize_db_config, save_db_profile, save_result_to_mariadb, test_mariadb_connection
from prompts import DEFAULT_USER_PROMPT


DB_SESSION_KEYS = {
    "host": "db_host",
    "port": "db_port",
    "user": "db_user",
    "password": "db_password",
    "database": "db_name",
    "main_table": "db_main_table",
    "detail_table": "db_detail_table",
    "main_key_column": "db_main_key_column",
    "detail_foreign_key": "db_detail_foreign_key",
}

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


def get_default_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("MARIADB_HOST", DEFAULT_DB_CONFIG["host"]),
        "port": int(os.getenv("MARIADB_PORT", str(DEFAULT_DB_CONFIG["port"]))),
        "user": os.getenv("MARIADB_USER", DEFAULT_DB_CONFIG["user"]),
        "password": os.getenv("MARIADB_PASSWORD", DEFAULT_DB_CONFIG["password"]),
        "database": os.getenv("MARIADB_DATABASE", DEFAULT_DB_CONFIG["database"]),
        "main_table": os.getenv("MARIADB_MAIN_TABLE", DEFAULT_DB_CONFIG["main_table"]),
        "detail_table": os.getenv("MARIADB_DETAIL_TABLE", DEFAULT_DB_CONFIG["detail_table"]),
        "main_key_column": os.getenv("MARIADB_MAIN_KEY_COLUMN", DEFAULT_DB_CONFIG["main_key_column"]),
        "detail_foreign_key": os.getenv("MARIADB_DETAIL_FOREIGN_KEY", DEFAULT_DB_CONFIG["detail_foreign_key"]),
    }


def apply_db_config_to_session(config: dict[str, Any]) -> None:
    normalized = normalize_db_config(config)
    for field_name, session_key in DB_SESSION_KEYS.items():
        st.session_state[session_key] = normalized[field_name]


def get_db_config_from_session() -> dict[str, Any]:
    return normalize_db_config(
        {
            field_name: st.session_state.get(session_key, DEFAULT_DB_CONFIG[field_name])
            for field_name, session_key in DB_SESSION_KEYS.items()
        }
    )


def load_selected_db_profile() -> None:
    selected_name = st.session_state.get("selected_db_profile_widget", "").strip()
    profiles = load_db_profiles()
    st.session_state["selected_db_profile"] = selected_name
    if not selected_name:
        return
    config = profiles.get(selected_name)
    if not config:
        return
    apply_db_config_to_session(config)
    st.session_state["db_profile_name"] = selected_name
    st.session_state["db_profile_name_widget"] = selected_name
    st.session_state["db_profile_feedback"] = {
        "type": "success",
        "message": f"DB 프로필 '{selected_name}'을 불러왔습니다.",
    }


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
    for key in ["edit_main_draft", "edit_detail_draft", "detail_visible_columns", "main_editor_dialog", "detail_editor_dialog"]:
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
        "db_profile_feedback": None,
        "db_connection_feedback": None,
        "selected_db_profile": "",
        "db_profile_name": "",
        "selected_db_profile_widget": "",
        "db_profile_name_widget": "",
        "refresh_db_profile_widgets": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    default_db_config = get_default_db_config()
    for field_name, session_key in DB_SESSION_KEYS.items():
        if session_key not in st.session_state:
            st.session_state[session_key] = default_db_config[field_name]

    initial_db_profiles = load_db_profiles()
    if not st.session_state.get("selected_db_profile") and initial_db_profiles:
        first_profile_name = sorted(initial_db_profiles.keys())[0]
        st.session_state["selected_db_profile"] = first_profile_name
        st.session_state["db_profile_name"] = first_profile_name
        st.session_state["selected_db_profile_widget"] = first_profile_name
        st.session_state["db_profile_name_widget"] = first_profile_name
        apply_db_config_to_session(initial_db_profiles[first_profile_name])

    if st.session_state.get("refresh_db_profile_widgets"):
        st.session_state["selected_db_profile_widget"] = st.session_state.get("selected_db_profile", "")
        st.session_state["db_profile_name_widget"] = st.session_state.get("db_profile_name", "")
        st.session_state["refresh_db_profile_widgets"] = False


def render_sidebar_settings() -> tuple[str, str, bool, str, str]:
    with st.sidebar:
        st.header("LLM 설정")
        endpoint_url = st.text_input("Endpoint URL", value="http://ai.paruda.com:11434/api/chat")
        model = st.text_input("Model", value="gemma4:e4b")
        api_key_required = st.toggle("API Key 필요", value=False)
        api_key = ""
        if api_key_required:
            api_key = st.text_input("API Key", type="password", placeholder="Bearer token")
        extra_prompt = st.text_area(
            "추가 프롬프트",
            value=DEFAULT_USER_PROMPT,
            height=420,
            help="JSON 추출 시 시스템 프롬프트에 더해 사용자 지시를 추가합니다.",
        )

        st.divider()
        with st.expander("MariaDB 저장 설정", expanded=False):
            db_profiles = load_db_profiles()
            profile_options = [""] + sorted(db_profiles.keys())

            st.caption("프로필 관리")
            st.selectbox(
                "저장된 프로필",
                options=profile_options,
                key="selected_db_profile_widget",
                format_func=lambda name: name or "선택 안 함",
                on_change=load_selected_db_profile,
            )
            st.text_input("프로필명", key="db_profile_name_widget", placeholder="예: 운영DB")
            profile_save_col, profile_delete_col = st.columns(2)
            with profile_save_col:
                if st.button("프로필 저장", use_container_width=True):
                    try:
                        profile_name = st.session_state.get("db_profile_name_widget", "").strip()
                        save_db_profile(profile_name, get_db_config_from_session())
                    except Exception as exc:
                        st.session_state["db_profile_feedback"] = {"type": "error", "message": f"프로필 저장 실패: {exc}"}
                    else:
                        st.session_state["selected_db_profile"] = profile_name
                        st.session_state["db_profile_name"] = profile_name
                        st.session_state["refresh_db_profile_widgets"] = True
                        st.session_state["db_profile_feedback"] = {"type": "success", "message": f"DB 프로필 '{profile_name}'을 저장했습니다."}
                        st.rerun()
            with profile_delete_col:
                if st.button("프로필 삭제", use_container_width=True):
                    try:
                        profile_name = st.session_state.get("selected_db_profile_widget", "").strip() or st.session_state.get("db_profile_name_widget", "").strip()
                        delete_db_profile(profile_name)
                    except Exception as exc:
                        st.session_state["db_profile_feedback"] = {"type": "error", "message": f"프로필 삭제 실패: {exc}"}
                    else:
                        st.session_state["selected_db_profile"] = ""
                        st.session_state["db_profile_name"] = ""
                        st.session_state["refresh_db_profile_widgets"] = True
                        apply_db_config_to_session(get_default_db_config())
                        st.session_state["db_profile_feedback"] = {"type": "success", "message": f"DB 프로필 '{profile_name}'을 삭제했습니다."}
                        st.rerun()

            profile_feedback = st.session_state.get("db_profile_feedback")
            if profile_feedback:
                getattr(st, profile_feedback["type"])(profile_feedback["message"])

            st.caption("접속 정보")
            host_col, port_col = st.columns([3, 2])
            with host_col:
                st.text_input("Host", key="db_host")
            with port_col:
                st.number_input("Port", min_value=1, max_value=65535, key="db_port")

            user_col, password_col = st.columns(2)
            with user_col:
                st.text_input("User", key="db_user")
            with password_col:
                st.text_input("Password", type="password", key="db_password")

            st.text_input("Database", key="db_name")
            if st.button("DB 연결 테스트", use_container_width=True):
                try:
                    message = test_mariadb_connection(get_db_config_from_session())
                except Exception as exc:
                    st.session_state["db_connection_feedback"] = {"type": "error", "message": f"DB 연결 실패: {exc}"}
                else:
                    st.session_state["db_connection_feedback"] = {"type": "success", "message": message}
                st.rerun()

            connection_feedback = st.session_state.get("db_connection_feedback")
            if connection_feedback:
                getattr(st, connection_feedback["type"])(connection_feedback["message"])

    return endpoint_url, model, api_key_required, api_key, extra_prompt


def render_main_section(main_data: Any) -> None:
    st.subheader("Main")
    if isinstance(main_data, dict):
        table_rows = [{"field": key, "value": value} for key, value in main_data.items()]
        if table_rows:
            st.dataframe(table_rows, use_container_width=True, hide_index=True)
        with st.expander("Main JSON 보기", expanded=False):
            st.code(json.dumps(main_data, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("main 값이 객체 형태가 아닙니다.")
        st.write(main_data)


def render_detail_section(detail_data: Any) -> None:
    st.subheader("Detail")
    if isinstance(detail_data, list):
        if detail_data:
            st.dataframe(detail_data, use_container_width=True, hide_index=True)
        with st.expander("Detail JSON 보기", expanded=False):
            st.code(json.dumps(detail_data, ensure_ascii=False, indent=2), language="json")
    else:
        st.warning("detail 값이 배열 형태가 아닙니다.")
        st.write(detail_data)


def render_extracted_tables(tables: list[dict[str, Any]]) -> None:
    st.subheader("추출된 표")
    if not tables:
        st.info("인식된 표가 없습니다. 이 경우 텍스트 추출 결과만 LLM에 전달됩니다.")
        return
    for table in tables:
        st.markdown(f"페이지 {table['page']} / 표 {table['table_index']}")
        st.dataframe(table["rows"], use_container_width=True)


@st.dialog("매칭 수정", width="large")
def render_edit_dialog() -> None:
    main_rows = st.session_state.get("edit_main_draft")
    detail_rows = st.session_state.get("edit_detail_draft")
    if main_rows is None or detail_rows is None:
        start_edit_session()
        main_rows = st.session_state.get("edit_main_draft", [])
        detail_rows = st.session_state.get("edit_detail_draft", [])

    st.markdown("Main 수정")
    edited_main_df = st.data_editor(pd.DataFrame(main_rows), use_container_width=True, num_rows="dynamic", key="main_editor_dialog")
    st.session_state["edit_main_draft"] = edited_main_df.to_dict(orient="records")

    st.markdown("Detail 수정")
    detail_df = pd.DataFrame(detail_rows)
    detail_columns = [column for column in detail_df.columns if column not in HIDDEN_DETAIL_COLUMNS]
    if not detail_df.empty and HIDDEN_DETAIL_COLUMNS:
        detail_df = detail_df[[column for column in detail_df.columns if column not in HIDDEN_DETAIL_COLUMNS]]
    if detail_columns:
        if "detail_visible_columns" not in st.session_state or not st.session_state["detail_visible_columns"]:
            st.session_state["detail_visible_columns"] = detail_columns[:]
        selected_visible_columns = st.multiselect(
            "보이는 Detail 컬럼",
            options=detail_columns,
            default=st.session_state.get("detail_visible_columns", detail_columns),
            key="detail_visible_columns",
            help="선택 해제한 컬럼은 현재 편집본에서 제외됩니다.",
        )
        detail_df = pd.DataFrame(
            [{key: value for key, value in row.items() if key in selected_visible_columns} for row in st.session_state.get("edit_detail_draft", [])]
        )

    edited_detail_df = st.data_editor(detail_df, use_container_width=True, num_rows="dynamic", key="detail_editor_dialog")
    st.session_state["edit_detail_draft"] = edited_detail_df.to_dict(orient="records")

    updated_result = {
        "main": editor_rows_to_main(st.session_state.get("edit_main_draft", [])),
        "detail": sanitize_detail_rows(st.session_state.get("edit_detail_draft", [])),
    }

    save_col, download_col, cancel_col = st.columns(3)
    with save_col:
        if st.button("저장", type="primary", use_container_width=True):
            try:
                save_result_to_mariadb(updated_result, get_db_config_from_session(), sanitize_detail_rows)
            except Exception as exc:
                st.error(f"MariaDB 저장 실패: {exc}")
            else:
                st.session_state["last_result"] = updated_result
                st.session_state["edit_mode"] = False
                clear_edit_session()
                st.session_state["save_feedback"] = {
                    "type": "success",
                    "message": "매칭 수정 내용을 저장했고 MariaDB 반영도 완료했습니다.",
                }
                st.rerun()
    with download_col:
        st.download_button(
            "JSON 다운로드",
            data=json.dumps(updated_result, ensure_ascii=False, indent=2),
            file_name="matched_result.json",
            mime="application/json",
            use_container_width=True,
        )
    with cancel_col:
        if st.button("취소", use_container_width=True):
            st.session_state["edit_mode"] = False
            clear_edit_session()
            st.rerun()
