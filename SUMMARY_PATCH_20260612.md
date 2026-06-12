# 🛠️ 2026-06-12 RAG 시스템 슬래시 명령어(/) 자동완성 및 실시간 UI 개선 패치 내역

본 문서는 사용자의 질문 입력창 슬래시 명령어(`/`) 제안 팝업 복구, 실시간 테두리선 두께 및 색상 피드백, 그리고 Streamlit Cloud 환경에서의 React 가상 돔 크래시 현상을 해결하기 위해 적용된 패치 및 설계 내용을 상세히 기록합니다.

---

## 1. ⚠️ 주요 해결 과제 및 진단 내용

### ① Minified React error #231 크래시
* **원인**: Streamlit `st.markdown(unsafe_allow_html=True)` 렌더러에 `onerror`나 `onload` 등의 이벤트 리스너 속성이 포함된 HTML 태그(예: `<img onerror="...">`)를 강제 삽입하면 React DOM validation이 이를 차단하고 전체 UI를 즉각 종료시켰습니다.
* **해결**: 모든 HTML 속성 기반의 이벤트 리스너를 제거하고, 브라우저가 DOM 삽입 즉시 스크립트를 로드하는 `<svg style='display:none;'><script>...</script></svg>` 구조로 전환하여 React Error #231을 원천 예방했습니다.

### ② SVG 내부 스크립트 XML SyntaxError 현상
* **원인**: `<svg>` 안쪽의 `<script>` 영역은 HTML이 아닌 **XML 스키마 규격**으로 엄격하게 파싱됩니다. 이로 인해 JS 코드 속의 비교 연산자 (`<`), 논리곱 연산자 (`&&`), 문자열 내 HTML 태그 (`'<span>'`) 등이 XML 태그의 시작이나 엔티티 기호로 오파싱되어 구문 오류(SyntaxError)를 유발하고 스크립트 실행이 중단되는 문제가 발생했습니다.
* **해결**: 스크립트 실행 범위를 `//<![CDATA[` 와 `//]]>` (Character Data) 주석 블록으로 감싸 XML 파서가 내부 특수 기호를 무시하고 순수 문자열 데이터로 넘기도록 해결했습니다.

### ③ Streamlit Markdown Parser의 개행(Blank Line) 분할 이슈
* **원인**: Streamlit의 마크다운 파서는 HTML 태그 내부라도 **빈 줄(Blank Line)**을 마주하면 태그 해석을 종료하고 그 뒷부분을 일반 마크다운/텍스트 노드로 split하는 특성을 보였습니다. 이로 인해 스크립트 닫는 중괄호 등이 화면에 텍스트로 누출되었습니다.
* **해결**: `GLOBAL_CSS` 내 스크립트 전체에서 모든 개행 및 공백 라인을 제거하여 하나의 raw HTML 블록으로 온전히 파싱되도록 단일화했습니다.

### ④ 카테고리 갱신 라이프사이클 지연 및 롤백 현상
* **원인**: Python 변수 주입 방식은 Streamlit의 가상 돔 재사용 특성으로 인해 category가 갱신되어도 브라우저 단에서 `<script>`가 재실행되지 않거나 실행 순서가 꼬여 테두리가 오렌지색에 갇히는 현상이 있었습니다.
* **해결**: Python 변수 전송용 코드를 모두 폐기하고, 브라우저 스크립트 인터벌(300ms) 내에서 **사이드바의 활성화된 버튼 DOM 상태(`[data-testid="stSidebar"] button[kind="primary"]`)를 직접 감지**하여 카테고리 상태와 질문창 테두리 색상(파랑)을 딜레이 없이 100% 매칭시켰습니다.
* **태그 독립형 선택자**: sidebar가 `<div>`가 아닌 `<section>`으로 렌더링되는 점을 파악해 `div` 태그 지정을 생략한 범용 CSS/JS 선택자로 고도화했습니다.

---

## 2. 📂 파일별 변경 사항

### 1) [app_config.py](file:///e:/내 드라이브/antigravity/sen-chatbot/app_config.py)
* **CSS 개선**: stChatInput 테두리선을 기본 2px에서 **5px**로 크게 넓혀 시각적 피드백(오렌지 / 초록 / 파랑)을 극대화했습니다.
* **자바스크립트 인터벌 보강**:
  * `window.autocompleteInterval` 식별자를 두어 리런 시 기존 동작 중이던 인터벌을 제거(`clearInterval`)하고 단 하나의 루프만 유지하여 리스너 누수를 막았습니다.
  * textarea에 `dataset.autocompleteBound = 'true'` 플래그를 설정하여 동일 노드에 대한 이중 리스너 등록을 원천 차단했습니다.
  * DOM 직접 조회를 통해 활성 카테고리를 추출하는 `getSelectedCategoryFromDOM()` 함수와 global fallback 탐색 통로를 추가했습니다.
  * script 영역 전체를 CDATA로 안전하게 감싸고 빈 줄을 완전 정화했습니다.

### 2) [app.py](file:///e:/내 드라이브/antigravity/sen-chatbot/app.py)
* 렌더링 도중 browser window 상태와 꼬이던 `st.markdown(cat_tracker)` SVG 주입 코드를 완전히 삭제하여 DOM 구조를 단순화하고 Rerun 속도를 높였습니다.

### 3) [simple_user_manual.md](file:///e:/내 드라이브/antigravity/sen-chatbot/simple_user_manual.md) & [simple_user_manual.html](file:///e:/내 드라이브/antigravity/sen-chatbot/simple_user_manual.html)
* 질문 입력창에 `/` 키를 입력했을 때 드롭다운 자동완성 창이 열리고 키보드로 이동하는 단축키 사용 매뉴얼 가이드를 전면 보강 및 복원했습니다.

---

## 3. 🧪 기능 테스트 및 검증 결과

* **구문 검사**: `py -m py_compile app.py app_config.py` 컴파일 성공.
* **배포 및 빌드**: main 브랜치 원격 push 성공으로 Streamlit Cloud 배포 인스턴스 자동 갱신.
* **테두리선 가시성**: 5px 변경 후 오렌지(자동 분류 Q&A), 초록(슬래시 명령어 활성), 파랑(특정 카테고리 강제 맵핑) 상태 전환이 원활히 동작하는 것 확인.
* **콘솔 모니터링**: React Error #231 및 XML Parsing SyntaxError 완전 소멸 검증 완료.
