# 🏛️ AI-SENSE SMART RAG SYSTEM 프로그래밍 기술서 (Technical Spec)

본 명세서는 서울시교육청 교육행정 지침 기반 지능형 챗봇 시스템에 적용된 핵심 소프트웨어 엔지니어링 설계, 클래스 구조, RAG 알고리즘 최적화 명세서 및 최근 반영된 고급 프론트엔드 스타일 오버라이딩 규칙을 상술합니다.

---

## 1. 아키텍처 및 시스템 흐름 (System Flowchart)

본 시스템은 외부 프레임워크 종속성을 배제하고, 로컬 연산 성능을 최대화할 수 있도록 순수 Python 및 고성능 모듈(`PyMuPDF`, `FAISS`, `Google Gemini API`)로 구축된 **단일 프로세스 파이프라인**을 제공합니다.

```mermaid
flowchart TD
    subgraph 1. 문서 전처리 단계 (PDF Extraction)
        A[manuals/*.pdf 로드] --> B[PyMuPDF 텍스트 파싱]
        A --> C[pymupdf.find_tables 표 검출]
        C --> D[table_to_markdown 격자 표 복원]
        B --> E[Recursive Character Splitter]
        D --> E
        E --> F[700자 청크 + 메타데이터 추출]
    end

    subgraph 2. 벡터 인덱싱 단계 (FAISS Indexing)
        F --> G[Google Gemini API gemini-embedding-2 다중 임베딩 생성]
        G --> H[L2 Normalization 정규화]
        H --> I[faiss.IndexFlatIP 코사인 유사도 인덱스 생성]
        I --> J[LocalVectorDB 직렬화 캐싱저장]
    end

    subgraph 3. RAG 추론 단계 (Query & Inference)
        K[사용자 질문 입력] --> L[Google Gemini API 쿼리 임베딩 생성 및 L2 정규화]
        L --> M[FAISS IndexFlatIP 초고속 서치]
        M --> N[0.5 유사도 Threshold 필터링 및 맥락 보강]
        N --> O[Gemini 2.5 Flash / Fallback LLM 호출]
        O --> P[출처 카드 연계 및 실시간 답변 렌더링]
    end
```

---

## 2. 핵심 클래스 설계 명세 (Class Specifications)

### 2.1. `RecursiveCharacterTextSplitter` (텍스트 분할 알고리즘)
무거운 프레임워크(LangChain 등)를 배제하고 속도와 제어 정밀성을 극대화하기 위해 직접 구현한 순수 파이썬 문자열 분할기입니다.

* **동작 원리**:
  1. 문자열 길이가 `chunk_size` 이하일 경우 즉시 리턴합니다.
  2. 사전에 설정된 구분자 리스트 `["\n\n", "\n", " ", ""]` 순서로 구분자가 본문에 존재하는지 스캔하고, 유효한 가장 큰 구분 기점으로 1차 재귀 분할을 실시합니다.
  3. 조각난 단락들을 재조합하면서 최대 크기를 넘기 직전까지 청크에 담습니다.
  4. 다음 청크로 넘어갈 때, 이전 청크의 마지막 부분을 `chunk_overlap` 크기만큼 가져와 겹치게(Overlap) 구성함으로써 문맥 흐름을 유지합니다.

```python
class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size=700, chunk_overlap=80, separators=None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]
        
    def split_text(self, text):
        return self._split_text(text, self.separators)
```

### 2.2. `LocalVectorDB` (고성능 로컬 검색 엔진)
인덱싱된 지침 텍스트, 원본 임베딩 정보, 그리고 FAISS 인덱스 인프라를 하나로 구조화하여 물리 디스크에 캐싱하고 검증하는 코어 클래스입니다.

* **메서드 및 기능 명세**:
  - `build_index()`: 
    - 생성된 NumPy 임베딩 행렬을 L2 정규화(`norms = np.linalg.norm(..., axis=1)`) 처리합니다.
    - 정규화된 벡터 행렬을 Meta의 초고속 유사도 탐색 라이브러리인 `faiss.IndexFlatIP` (Inner Product)에 주입합니다. 이를 통해 Inner Product 연산이 코사인 유사도(Cosine Similarity) 연산과 기하학적으로 완벽히 일치하게 유도됩니다.
  - `save_local(folder_path, current_hash)`:
    - 폴더 내용물 검증을 위해 계산된 MD5 해시 정보와 정제된 텍스트 청크, 임베딩 행렬을 직렬화 패키징하여 `.vector_cache.pkl`에 바이너리 파일로 안전하게 기록합니다.
  - `load_local(folder_path, current_hash)`:
    - 저장된 캐시가 존재하고, 전달받은 신규 폴더 해시 정보와 캐시 파일 내에 기록된 해시가 정확히 일치할 때만 인덱스를 디스크에서 읽어 즉시 로드하고 FAISS 메모리 인덱스를 재빌드합니다.

---

## 3. 핵심 RAG 파이프라인 함수 명세 (Core Pipeline Functions)

### 3.1. `table_to_markdown(table_data)` (PDF 표 구조 복원 엔진)
* **목적**: PDF 페이지 내부의 비정형 표 데이터를 무손실 상태의 마크다운 표 양식으로 인코딩하여 LLM의 표 이해도를 극대화합니다.
* **로직**:
  - `pymupdf`의 `page.find_tables()`가 반환한 2차원 리스트 행렬을 입력받습니다.
  - 행렬을 스캔하며 비어있거나 무효한 행(Row)을 검출해 예외 처리합니다.
  - 개행 문자(`\n`)를 공백(` `)으로 일괄 치환하여 마크다운 표 깨짐 현상을 차단합니다.
  - 표의 헤더 경계선(`| --- | --- |`)을 동적으로 삽입하여 완벽한 정형 표를 재조합합니다.

### 3.2. `get_pdf_chunks(folder_path)` (고성능 레이아웃 전처리)
* **목적**: 디렉토리 내부의 모든 PDF를 순회하며 일반 텍스트 및 정형 표를 의미 청크로 다차원 결합합니다.
* **로직**:
  - PyMuPDF(`fitz.open()`) 엔진을 가동합니다.
  - 각 페이지에 대해 일반 텍스트(`page.get_text()`)와 결합 테이블 마크다운을 연계 병합합니다.
  - [RecursiveCharacterTextSplitter]를 연계 호출하여 `700자 / 80자 중첩` 메타 청크로 변환합니다.
  - 메타데이터 포맷: `[파일명 - {page_num}p (분할 {chunk_idx})]` 형식으로 자동 구조화하여 원천 파일과 위치를 정확히 맵핑합니다.

### 3.3. `retrieve_top_chunks(query, category, k=15, threshold=0.5)` (유사도 하한 필터링 검색)
* **목적**: FAISS 인덱스를 탐색하여 최상위 유효 조각들을 초정밀 필터링합니다.
* **로직**:
  - 질문 텍스트 `query`를 Google Gemini API(`gemini-embedding-2` 모델)로 실시간 임베딩 변환하고 쿼리 벡터를 얻습니다.
  - 쿼리 벡터 역시 L2 정규화 처리 후 FAISS의 `index.search()` 함수에 전달하여 Inner Product 거리 기준 탑-K 서치를 수행합니다.
  - 매칭 스코어가 **0.5 이상**인 데이터만 유효 인덱스로 분류하여 수용하고, 이외의 무관 조각들은 전면 제거하여 정보 오염을 원천 차단합니다.
  - **맥락 보강 (Context Reinforcement)**: 검색 적중한 청크(`idx`)의 원문뿐만 아니라, 동일 PDF 문서 내 직전 청크(`idx - 1`) 및 직후 청크(`idx + 1`)까지 3개 청크를 유기적으로 연결하여 AI에 풍부한 전후 맥락 컨텍스트를 제공합니다.

---

## 4. UI/UX 및 견고한 Fallback 메커니즘 설정

### 4.1. Step Status 및 사용자 보호
- **대기 단계 안내**: `.vector_cache.pkl`이 존재하지 않는 분야일 경우 일반 유저가 진입하면 `st.stop()`으로 UI 조작을 일시 제한하고, 정중하고 아름다운 설명 패널과 함께 관리자 호출 경고 로그를 자동 기록합니다.
- **실시간 Status**: RAG 검색 시 `st.status` 컴포넌트를 사용하여 탐색, 임계 필터링, AI 작성 단계를 체크리스트 및 스피너 그래픽으로 보여줍니다.

### 4.2. Gemini 다중 Fallback 및 버그 패치
- 사용 가능한 Gemini 가용 모델(1.5, 2.0, 2.5 등)들을 API 응답 특성 및 토큰 할당량에 따라 자동 우선순위 배열하여 바인딩합니다.
- 특정 모델 장애 시 구형 SDK(`legacy_generativeai`)로 우회 처리하며, 루프 내부에서 오류 이력을 관리하기 위해 `errors = []` 초기화 버그를 패치하여 런타임 NameError를 영구 제거했습니다.
- 검색 결과가 없을 경우 환각 예외 방어 프롬프트 ("공식 지침서 근거를 찾지 못했습니다")를 연계 동작하도록 보강했습니다.

---

## 5. UI/UX CSS 최적화 및 정렬 시스템 명세 (UI/UX Engineering)

본 프로그램은 Streamlit 프레임워크의 구조적 제약과 벌키(Bulky)한 여백 레이아웃을 극복하기 위해 강력한 **CSS 주입(Custom Injecting)** 및 **동적 데이터 가중치 정렬**을 구현하였습니다.

### 5.1. Streamlit 그리드 강제 오버라이딩 (Ultra-Compact Sidebar Gaps)
Streamlit은 기본적으로 위젯 요소 사이에 넓은 여백을 고정 배치합니다. 이를 극복하고자 하단 CSS 규칙을 주입하여 레이아웃을 종이 한 장 두께로 초압축시켰습니다.

```css
/* 사이드바 내부 엘리먼트 간의 Streamlit 기본 외부 간격 극단적으로 축소 */
[data-testid="stSidebar"] [data-testid="element-container"] {
    margin-bottom: 2px !important;
    padding-bottom: 0px !important;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 2px !important;
}
```

### 5.2. 글로벌 좌측 정렬 규칙 (Global Sidebar Left-Alignment)
사이드바 내의 버튼과 다운로드 버튼이 항상 완벽한 피드로 좌측에 안착되도록 강제하는 고해상도 고순도 CSS 셀렉터 세트입니다.

```css
/* 사이드바 내부의 모든 버튼 및 내부 자식 요소 강제 좌측 정렬 */
[data-testid="stSidebar"] button {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
}
[data-testid="stSidebar"] button div[data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] button p,
[data-testid="stSidebar"] button span {
    width: 100% !important;
    text-align: left !important;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 6px !important;
    margin: 0 !important;
}
```

### 5.3. 브라우저 네이티브 파일명 유동 말줄임 (Dynamic CSS Ellipsis)
서버단에서의 임의의 글자수 Truncate 대신 브라우저의 폭에 연계하여 파일명이 최대 너비를 채우고, 이를 벗어나면 자동으로 안전하게 말줄임표를 다는 특성을 주입했습니다.

```css
/* 넘치는 파일명 자동 말줄임(Ellipsis) 적용 */
.file-container .stDownloadButton > button div[data-testid="stMarkdownContainer"],
.file-container .stDownloadButton > button p,
.file-container .stDownloadButton > button span {
    width: 100% !important;
    text-align: left !important;
    display: inline-block !important; /* text-overflow 활성화를 위한 블록화 */
    white-space: nowrap !important;
    text-overflow: ellipsis !important;
    overflow: hidden !important;
    vertical-align: middle !important;
    margin: 0 !important;
}
```

### 5.4. 가중치 기반 동적 정렬 키 (Hangul Alphabetical Sort Key)
카테고리 폴더 리스트를 한글 가나다순으로 깔끔하게 정렬하되, 업무 지침상 예외 분류인 '기타' 폴더를 정렬 키 가중치를 조절하여 마지막으로 보내는 다차원 lambda 정렬 연산을 수행합니다.

```python
categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d))]
# 가나다순 오름차순 정렬을 수행하면서 '기타'를 포함하는 항목은 튜플 첫 키 가중치를 1로 주어 맨 뒤로 정렬시킴
categories = sorted(categories_raw, key=lambda x: (1 if "기타" in x else 0, x))
```

---

## 6. 신규 빌드 및 동기화 자동화 명세 (CLI & Automation Spec)

기존 분석 시스템의 속도 한계 및 동기화 작업 편의성을 극대화하기 위해 다차원 자동화 아키텍처가 도입되었습니다.

### 6.1. Google Gemini API Batch Embedding 버그 수정
* **버그**: 기존 코드에서 리스트 형식으로 배치 데이터를 전달할 때 SDK가 이를 하나의 거대한 단일 문서로 취급하여 다중 텍스트임에도 1개의 벡터만 생성해 내어 검색 기능이 고장 났었습니다.
* **패치**: 각 배치 문장을 명시적인 `types.Content` 구조체 리스트로 명시하여 각각의 독립된 임베딩 벡터로 생성되도록 조치했습니다.
```python
contents_batch = [types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]
response = client.models.embed_content(
    model="gemini-embedding-2",
    contents=contents_batch
)
```

### 6.2. 지능형 폴더 해시(Hash) 스캔 및 변경 감지 알고리즘
* **목적**: 변경되지 않은 지침서 카테고리를 다시 임베딩하는 등의 불필요한 구글 API 호출 낭비를 영구적으로 차단합니다.
* **구현**:
  1. 각 폴더 내부의 모든 PDF 파일의 개수, 명칭, 용량 및 적용 모델명을 종합하여 **MD5 해시 키**를 생성합니다.
  2. 디스크의 캐시 파일(`.vector_cache.pkl`)의 해시값과 현재 실시간 생성된 해시값을 비교합니다.
  3. 해시가 동일한 경우 즉시 로딩을 건너뛰고(`변경 없음`), 불일치하는 경우에만 신규 파싱 및 API 임베딩 호출을 진행합니다.
  4. PDF 파일이 0개인 빈 폴더는 탐색 루프에서 원천 건너뜁니다.

### 6.3. Git Status Porcelain 기반의 Zero-Touch 업로드 자동화 (`sync.bat`)
* **원리**: 사용자의 별도 입력 없이 더블클릭 한 번으로 변경 사항 탐색부터 클라우드 배포 업로드까지의 흐름을 단일 스레드로 캡슐화합니다.
* **로직**:
  1. `build_cache.py`를 호출하여 모든 폴더의 변경 여부 스캔 및 부분 캐시 빌드를 진행합니다.
  2. 빌드 스크립트 실행이 끝난 후 `git status --porcelain` 명령어를 활용하여 실제 디렉토리에 변경(수정/추가/삭제)된 임베딩 캐시 및 PDF 파일이 존재하는지 모니터링합니다.
  3. 변경 상태 값이 감지되었을 때만 `git push` 파이프라인을 자동 발동하며, 변경 사항이 없는 경우 네트워크 푸시 요청을 차단하여 자원을 보호합니다.
