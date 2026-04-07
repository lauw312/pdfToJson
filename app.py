from __future__ import annotations

import json
from hashlib import md5

import streamlit as st

from llm_utils import request_json_from_llm
from pdf_utils import extract_pdf_tables_cached, extract_pdf_text_cached
from ui_utils import (
    clear_edit_session,
    init_session_state,
    render_detail_section,
    render_edit_dialog,
    render_extracted_tables,
    render_main_section,
    render_sidebar_settings,
    start_edit_session,
)


st.set_page_config(page_title="PDF to JSON Analyzer", layout="wide")
st.title("PDF to JSON Analyzer")
st.caption("PDF 텍스트를 추출하고 LLM API로 main/detail JSON을 생성합니다.")

init_session_state()
endpoint_url, model, api_key_required, api_key, extra_prompt = render_sidebar_settings()

upload_col, action_col = st.columns([4, 1])
with upload_col:
    uploaded_file = st.file_uploader("PDF 파일 업로드", type=["pdf"])
with action_col:
    st.write("")
    st.write("")
    extract_button = st.button("JSON 추출", type="primary", use_container_width=True)

if extract_button:
    if not uploaded_file:
        st.error("먼저 PDF 파일을 업로드해 주세요.")
    elif not st.session_state.get("pdf_text", "").strip():
        st.error("PDF에서 텍스트를 추출하지 못했습니다.")
    elif api_key_required and not api_key.strip():
        st.error("API Key를 입력해 주세요.")
    else:
        st.session_state.pop("last_result", None)
        st.session_state["edit_mode"] = False
        clear_edit_session()
        st.session_state["is_extracting"] = True
        st.rerun()

pdf_text = ""
pdf_tables = []
if uploaded_file is not None:
    try:
        pdf_bytes = uploaded_file.getvalue()
        current_file_hash = md5(pdf_bytes).hexdigest()
        if st.session_state["uploaded_file_hash"] != current_file_hash:
            st.session_state["uploaded_file_hash"] = current_file_hash
            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["pdf_text"] = extract_pdf_text_cached(pdf_bytes)
            st.session_state["pdf_tables"] = extract_pdf_tables_cached(pdf_bytes)
            st.session_state["edit_mode"] = False
            clear_edit_session()
        pdf_text = st.session_state["pdf_text"]
        pdf_tables = st.session_state["pdf_tables"]
    except Exception as exc:
        st.error(f"PDF 읽기 실패: {exc}")
else:
    st.session_state["uploaded_file_hash"] = ""
    st.session_state["pdf_bytes"] = b""
    st.session_state["pdf_text"] = ""
    st.session_state["pdf_tables"] = []
    clear_edit_session()

left_col, right_col = st.columns(2)

with left_col:
    with st.expander("추출된 텍스트", expanded=True):
        if pdf_text:
            st.text_area("PDF Text Preview", value=pdf_text, height=500)
        else:
            st.info("PDF를 업로드하면 여기에서 추출된 텍스트를 확인할 수 있습니다.")
    with st.expander("추출된 표", expanded=True):
        render_extracted_tables(pdf_tables)

with right_col:
    st.subheader("JSON 결과")
    if st.session_state.get("is_extracting"):
        st.info("JSON 추출 중입니다...")
        st.progress(35)
    elif "last_result" in st.session_state:
        result = st.session_state["last_result"]
        render_main_section(result.get("main"))
        render_detail_section(result.get("detail"))
        feedback = st.session_state.get("save_feedback")
        if feedback:
            getattr(st, feedback["type"])(feedback["message"])
        next_col, download_col = st.columns(2)
        with next_col:
            if st.button("다음", use_container_width=True):
                st.session_state["save_feedback"] = None
                start_edit_session()
                st.session_state["edit_mode"] = True
                st.rerun()
        with download_col:
            st.download_button(
                "JSON 다운로드",
                data=json.dumps(result, ensure_ascii=False, indent=2),
                file_name="extracted_result.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("아직 생성된 JSON 결과가 없습니다.")

if st.session_state.get("edit_mode") and "last_result" in st.session_state:
    render_edit_dialog()

if st.session_state.get("is_extracting") and uploaded_file is not None and pdf_text.strip():
    with st.spinner("LLM으로 JSON 추출 중입니다..."):
        try:
            result = request_json_from_llm(
                api_key=api_key.strip(),
                api_key_required=api_key_required,
                endpoint_url=endpoint_url.strip(),
                model=model.strip(),
                pdf_text=pdf_text,
                tables=pdf_tables,
                extra_prompt=extra_prompt,
            )
            st.session_state["last_result"] = result
            st.session_state["is_extracting"] = False
            st.success("JSON 추출이 완료되었습니다.")
            st.rerun()
        except Exception as exc:
            st.session_state["is_extracting"] = False
            st.error(f"JSON 추출 실패: {exc}")
