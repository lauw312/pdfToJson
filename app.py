from __future__ import annotations

import json
from hashlib import md5
from typing import Any

import streamlit as st

from core import extract_pdf_tables_cached, extract_pdf_text_cached, request_json_from_llm
from ui import (
    clear_edit_session,
    init_session_state,
    render_detail_section,
    render_edit_dialog,
    render_extracted_tables,
    render_main_section,
    render_sidebar_settings,
    start_edit_session,
)


def reset_pdf_state() -> None:
    st.session_state["uploaded_file_hash"] = ""
    st.session_state["pdf_bytes"] = b""
    st.session_state["pdf_text"] = ""
    st.session_state["pdf_tables"] = []
    clear_edit_session()


def load_uploaded_pdf(uploaded_file: Any) -> tuple[str, list[dict[str, Any]]]:
    pdf_bytes = uploaded_file.getvalue()
    current_file_hash = md5(pdf_bytes).hexdigest()

    if st.session_state["uploaded_file_hash"] != current_file_hash:
        st.session_state["uploaded_file_hash"] = current_file_hash
        st.session_state["pdf_bytes"] = pdf_bytes
        st.session_state["pdf_text"] = extract_pdf_text_cached(pdf_bytes)
        st.session_state["pdf_tables"] = extract_pdf_tables_cached(pdf_bytes)
        st.session_state["edit_mode"] = False
        clear_edit_session()

    return st.session_state["pdf_text"], st.session_state["pdf_tables"]


st.set_page_config(page_title="PDF to JSON Analyzer", layout="wide")
st.title("PDF to JSON Analyzer")
st.caption("PDF ?띿뒪?몃? 異붿텧?섍퀬 LLM API濡?main/detail JSON???앹꽦?⑸땲??")

init_session_state()
endpoint_url, model, api_key_required, api_key, extra_prompt = render_sidebar_settings()

upload_col, action_col = st.columns([4, 1])
with upload_col:
    uploaded_file = st.file_uploader("PDF ?뚯씪 ?낅줈??", type=["pdf"])
with action_col:
    st.write("")
    st.write("")
    extract_button = st.button("JSON 異붿텧", type="primary", use_container_width=True)

if extract_button:
    if not uploaded_file:
        st.error("癒쇱? PDF ?뚯씪???낅줈?쒗빐 二쇱꽭??")
    elif not st.session_state.get("pdf_text", "").strip():
        st.error("PDF?먯꽌 ?띿뒪?몃? 異붿텧?섏? 紐삵뻽?듬땲??")
    elif api_key_required and not api_key.strip():
        st.error("API Key瑜??낅젰??二쇱꽭??")
    else:
        st.session_state.pop("last_result", None)
        st.session_state["edit_mode"] = False
        clear_edit_session()
        st.session_state["is_extracting"] = True
        st.rerun()

pdf_text = ""
pdf_tables: list[dict[str, Any]] = []
if uploaded_file is not None:
    try:
        pdf_text, pdf_tables = load_uploaded_pdf(uploaded_file)
    except Exception as exc:
        st.error(f"PDF ?쎄린 ?ㅽ뙣: {exc}")
else:
    reset_pdf_state()

left_col, right_col = st.columns(2)

with left_col:
    with st.expander("異붿텧???띿뒪??, expanded=True):
        if pdf_text:
            st.text_area("PDF Text Preview", value=pdf_text, height=500)
        else:
            st.info("PDF瑜??낅줈?쒗븯硫??ш린?먯꽌 異붿텧???띿뒪?몃? ?뺤씤?????덉뒿?덈떎.")
    with st.expander("異붿텧????, expanded=True):
        render_extracted_tables(pdf_tables)

with right_col:
    st.subheader("JSON 寃곌낵")
    if st.session_state.get("is_extracting"):
        st.info("JSON 異붿텧 以묒엯?덈떎...")
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
            if st.button("?ㅼ쓬", use_container_width=True):
                st.session_state["save_feedback"] = None
                start_edit_session()
                st.session_state["edit_mode"] = True
                st.rerun()
        with download_col:
            st.download_button(
                "JSON ?ㅼ슫濡쒕뱶",
                data=json.dumps(result, ensure_ascii=False, indent=2),
                file_name="extracted_result.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("?꾩쭅 ?앹꽦??JSON 寃곌낵媛 ?놁뒿?덈떎.")

if st.session_state.get("edit_mode") and "last_result" in st.session_state:
    render_edit_dialog()

if st.session_state.get("is_extracting") and uploaded_file is not None and pdf_text.strip():
    with st.spinner("LLM?쇰줈 JSON 異붿텧 以묒엯?덈떎..."):
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
            st.success("JSON 異붿텧???꾨즺?섏뿀?듬땲??")
            st.rerun()
        except Exception as exc:
            st.session_state["is_extracting"] = False
            st.error(f"JSON 異붿텧 ?ㅽ뙣: {exc}")

