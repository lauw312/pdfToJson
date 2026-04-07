PDF 텍스트를 분석해서 핵심 정보를 main/detail 구조의 JSON으로 정리해줘.
- detail 값의 경우 추출된 표와 비교하여 값을 매칭해줘.

{
  "main": {
    "INSP_ID": "",        // 성적서 내부 관리 번호
    "ATCH_FILE_ID": "",   // 연결 첨부파일 ID
    "ATCH_SEQ": "",       // 연결 첨부파일 순번
    "APP_SEQ": "",        // 연결 결재/신청 순번
    "INSP_NO": "",        // 발급 번호
    "ISSUE_DT": "",       // 발급 일자
    "CUST_NM": "",        // 업소명(의뢰인)
    "COMP_ADDR": "",      // 소재지
    "PROD_NM": "",        // 제품명
    "INSP_PURP": "",      // 검사 목적
    "MAT_TYPE": "",       // 재질
    "MFG_DT": "",         // 제조 일자
    "RECV_DT": "",        // 접수 일자
    "COMPL_DT": ""        // 검사 완료 일자
  },
  "detail": [
    {
      "INSP_DTL_ID": "",   // 상세 순번 ID 시퀀스
      "INSP_ID": "",       // 마스터 ID 외래키
      "ITEM_SEQ": "",      // 항목 순서
      "INSP_ITEM": "",     // 검사 항목
      "TEST_METHOD": "",   // 시험 방법
      "UNIT": "",          // 단위
      "STD_VALUE": "",     // 기준
      "RESULT_VALUE": "",  // 결과
      "ITEM_JUDGE": ""     // 항목 판정
    }
  ]
}
추출값은 이 JSON 형태를 참조해서 정리해줘.
1. 각 검사 항목을 하나의 객체로 추출할 것
2. 추출 대상 필드: 검사항목(INSP_ITEM), 단위(UNIT), 기준(STD_VALUE), 결과(RESULT_VALUE), 항목판정(ITEM_JUDGE)
3. 빈 값은 null로 표기할 것
4. 단위(UNIT)와 기준값(STD_VALUE)이 모두 없는 행은 detail추출에서 제외할 것.
5. JSON 배열 형식으로만 응답하고, 마크다운 코드블록이나 부가 설명 없이 순수 JSON만 출력할 것

- detail의 '기준값(공백제거)'은 'STD_VALUE' 각 row당 배당
- detail의 'TEST_METHOD'은 표의 '시험방법' 값을 각 row당 배당.
