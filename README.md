# PDF to JSON Analyzer

PDF 파일을 업로드하고 텍스트를 추출한 뒤, 지정한 LLM HTTP API를 호출해서 `main` / `detail` 구조의 JSON으로 정리하는 Streamlit 앱입니다.

## 기능

- PDF 업로드
- PDF 텍스트 추출 및 미리보기
- `pdfplumber` 기반 표 추출 및 표 미리보기
- Endpoint URL / Model 직접 설정
- API Key 필요 여부에 따라 입력창 표시/숨김
- 추가 프롬프트 입력
- `JSON 추출` 버튼으로 LLM 호출
- 결과를 `main` / `detail` JSON과 테이블로 분리 출력

## 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 기본 연결값

- Endpoint URL: `http://ai.paruda.com:11434/api/chat`
- Model: `gemma4:e4b`
- API Key 필요: `해제`

## JSON 기대 구조

```json
{
  "main": {
    "document_type": "invoice",
    "title": "Sample Document",
    "organization": "ABC Corp",
    "date": "2026-04-07",
    "summary": "..."
  },
  "detail": [
    {
      "category": "header",
      "field": "invoice_number",
      "value": "INV-001",
      "confidence": "high",
      "evidence": "Invoice No. INV-001"
    }
  ]
}
```

## 참고

- 기본 구현은 Ollama 스타일의 `/api/chat` 응답 형식을 기준으로 작성했습니다.
- 응답 본문에서 `message.content`를 우선 읽고, 없으면 `response` 필드를 확인합니다.
- 디지털 PDF의 표는 `pdfplumber`로 셀 단위 추출을 먼저 시도합니다.
- 병합셀로 비는 값은 위 행 기준으로 보정해서 LLM에 전달합니다.
- 스캔본 PDF는 OCR이 없으면 표 매칭률이 제한될 수 있습니다.
