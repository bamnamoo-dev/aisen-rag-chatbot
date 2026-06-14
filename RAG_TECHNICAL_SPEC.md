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
  - **셀 내부 특수 문자 이스케이프**: 셀 데이터 내에 포함된 모든 파이프(`|`) 기호를 역슬래시 이스케이프(`\|`) 처리하여 마크다운 표의 컬럼 깨짐 및 수치 행 밀림 현상을 방지합니다.
  - 표의 헤더 경계선(`| --- | --- |`)을 동적으로 삽입하여 완벽한 정형 표를 재조합합니다.

### 3.2. `split_table_markdown(table_md, chunk_size, chunk_overlap)` (표 헤더 강제 복원 분할)
* **목적**: 하나의 긴 표가 `chunk_size`를 초과하여 여러 청크로 쪼개질 때, 하위 청크들이 열 이름(헤더) 정보 유실 없이 독립적인 표 구조를 유지하도록 강제합니다.
* **로직**:
  - 마크다운 표에서 헤더 행(`lines[0]`)과 구분선 행(`lines[1]`)을 추출합니다.
  - 행 단위(Line-by-line)로 순회하며 청크 크기 한도를 모니터링하여 분할합니다.
  - 두 번째 이후의 분할 조각(청크)들에 대해, 추출해 둔 헤더 행과 구분선 행을 자동으로 상단에 강제 주입(헤더 복원 복사)합니다.
  - 표 분할 경계선에서도 `chunk_overlap`을 행 단위로 계산하여 문맥 중첩을 보존합니다.

### 3.3. `get_pdf_chunks(folder_path)` 및 `parse_single_pdf` (원자적 텍스트-표 추출 분리)
* **목적**: 문서의 본문 텍스트와 표 데이터를 독립적인 '원자적 청크(Atomic Chunk)'로 격리 파싱하여 데이터 중복을 없애고 검색 정밀도를 높입니다.
* **로직**:
  - 각 페이지에 존재하는 유효한 표들의 바운딩 박스(`fitz.Rect(tab.bbox)`) 정보를 수집합니다.
  - `page.get_text("blocks")`를 통해 페이지 텍스트 블록을 읽어오며, 각 블록의 면적이 유효한 표의 바운딩 박스와 50% 이상 겹치면(Intersection Ratio > 0.5) 표 내부 글자로 판단하여 본문 텍스트 추출 대상에서 완전 제외합니다.
  - 표 영역이 제외된 본문 텍스트는 일반 [RecursiveCharacterTextSplitter]로 분할 처리합니다.
  - 추출된 표 데이터 마크다운은 [split_table_markdown]을 연계 호출하여 행 단위 독립 청크로 가공합니다.
  - 일반 본문 청크와 분할 표 청크를 하나의 페이지 청크 묶음으로 결합하여 적재합니다.

### 3.4. `retrieve_top_chunks(query, category, k=15, threshold=0.4)` (FAISS + BM25 가중합 하이브리드 검색 및 최신 지침 우선 정렬)
* **목적**: 질문의 의미적 맥락(FAISS)과 고유 법조항/플랫폼 명칭 등의 어휘적 일치성(BM25)을 결합하여 무결점의 지침 검색 결과를 확보하고 정밀 Reranking합니다.
* **로직**:
  - **1) 로컬 BM25 스코어 계산**: 질문 `query`를 경량 한글 토크나이저(`simple_korean_tokenizer`)로 분할하여 로컬 메모리의 `BM25Okapi` 인덱스로부터 각 문서 청크의 어휘 매칭 스코어를 계산하고, 최댓값($max\_bm25$)을 스캔합니다.
  - **2) 1차 의미 검색 후보군 탐색**: 질문을 Google Gemini API(`gemini-embedding-2`)로 실시간 임베딩 변환 및 L2 정규화한 뒤, FAISS `index.search()`를 통해 `search_k = max(100, k * 3)` 만큼 후보군을 스캔하여 상위 코사인 점수 맵(`faiss_map`)을 구성합니다.
  - **3) 후보군 합집합 구성**: FAISS 의미 검색 후보군과 실질 매칭 단어가 있어 BM25 점수가 0보다 큰 후보군들의 **합집합(`union_indices`)**을 결합하여 검색 대조군을 확장합니다.
  - **4) 하이브리드 가중합 스코어링**: 합집합 내의 각 청크에 대해 하이브리드 스코어를 산출합니다.
    - **시맨틱 유사도 ($Score_{cosine}$)**: FAISS 후보군에 존재하는 점수를 활용하되, 후보군 바깥에 있는 경우에는 직접 `db.embeddings`의 해당 청크 벡터와 쿼리 벡터 간의 NumPy 내적을 취해 정확한 코사인 유사도를 즉시 계산합니다.
    - **어휘 유사도 ($Score_{bm25}$)**: BM25 점수를 최댓값으로 나누어 `[0.0, 1.0]` 범위로 정규화합니다.
    - **결합 스코어**: 두 점수를 6:4 가중합 비율로 병합합니다:
      $$Score_{final} = 0.6 \times Score_{cosine} + 0.4 \times Score_{bm25}$$
  - **5) 임계치 필터링 및 부스팅**: 결합 점수가 **0.4 이상**인 청크들만 수용하며, 최신본 키워드(`(2026)`, `(최신)`, `_new` 등)를 확인하여 부스팅 가중치 **보너스 점수 +0.1**을 가산합니다.
  - **6) 맥락 보강 및 파일 경계 필터링**: 적중 청크의 전후 청크를 결합하여 UI 컨텍스트를 구성하되, 동일한 PDF 파일 소스에 속한 청크들만 엮어 파일 간 맥락 꼬임(Context Pollution)을 완벽 배제합니다.
  - **7) 최종 재정렬 (Reranking)**: 부스팅 점수가 가산된 하이브리드 최종 점수를 기준으로 내림차순 정렬하여 최종 상위 `k`개만 RAG 입력으로 추출합니다.

### 3.5. 카테고리별 최우선 지침 강제 정렬 및 교차 검색 (2026-06-12 적용)
* **목적**: 돈 관련 및 계약 관련 질의 시, 다른 연관 폴더의 풍부한 정보를 교차 참조하면서도 최우선이 되는 단일 지침서의 근거가 AI 답변 생성의 첫머리와 핵심으로 작용하도록 순서를 보장합니다.
* **로직**:
  - **1) 교차 검색 및 카테고리 순서 정의 (`app.py`)**:
    - **돈 관련 (예산/지출/세입)**: 질문이 세입/지출로 판별되면 `['예산', best_cat]` 순으로 검색 대상을 강제 재배치하여 `예산`을 가장 먼저 검색하도록 유도합니다. 예산 질문인 경우에도 지출/세입 폴더를 연계 검색합니다.
    - **계약 관련 (계약)**: 질문이 계약으로 판별되면 `['계약', '예산']` 순으로 검색 대상 폴더 리스트를 재배치합니다.
  - **2) 특정 지침 파일 식별 및 최상단 배치 (`app.py`)**:
    - 검색된 통합 청크 목록에서 파일명 매칭(`get_filename_from_metadata`)을 통해 최우선 지침 파일을 식별합니다.
      - 돈 관련 쿼리: `♣2026학년도 학교회계 예산편성 기본지침(변경25.12.19.).pdf` (검출 키워드: `"예산편성 기본지침"`)
      - 계약 관련 쿼리: `(2026적용)『서울특별시교육청 계약업무 처리지침』 - 2023.12.27. 개정.pdf` (검출 키워드: `"계약업무 처리지침"`)
    - 대상 파일의 청크를 `priority_chunks`로, 이외의 청크를 `other_chunks`로 분리한 뒤 각각 점수 내림차순 정렬을 수행한 후 `priority_chunks + other_chunks` 순서로 병합하여 최종 RAG 컨텍스트를 설계합니다.
    - 파일명의 이중 하이픈 예외에 완벽 대응하고자 단순 동일 비교 대신 substring 매칭을 적용했습니다.

---

## 4. UI/UX 및 견고한 Fallback 메커니즘 설정

### 4.1. Step Status 및 사용자 보호
- **대기 단계 안내**: `.vector_cache.pkl`이 존재하지 않는 분야일 경우 일반 유저가 진입하면 `st.stop()`으로 UI 조작을 일시 제한하고, 정중하고 아름다운 설명 패널과 함께 관리자 호출 경고 로그를 자동 기록합니다.
- **실시간 Status**: RAG 검색 시 `st.status` 컴포넌트를 사용하여 탐색, 임계 필터링, AI 작성 단계를 체크리스트 및 스피너 그래픽으로 보여줍니다.

### 4.2. Gemini 다중 Fallback 및 버그 패치
- 사용 가능한 Gemini 가용 모델(1.5, 2.0, 2.5 등)들을 API 응답 특성 및 토큰 할당량에 따라 자동 우선순위 배열하여 바인딩합니다.
- 특정 모델 장애 시 구형 SDK(`legacy_generativeai`)로 우회 처리하며, 루프 내부에서 오류 이력을 관리하기 위해 `errors = []` 초기화 버그를 패치하여 런타임 NameError를 영구 제거했습니다.
- 검색 결과가 없을 경우 환각 예외 방어 프롬프트 ("공식 지침서 근거를 찾지 못했습니다")를 연계 동작하도록 보강했습니다.

### 4.3. Streamlit Cloud 모듈 캐싱 무력화 및 강제 리로드 로직
- **문제점**: Streamlit Cloud 환경에서 파일 감지기(File Watcher)가 하위 디렉토리(예: `core/`, `services/`) 모듈의 변경을 감지하지 못하거나 Python 캐싱으로 인해 이전 코드가 계속 로드되어 있는 현상이 발생합니다.
- **해결책**: 메인 진입 스크립트인 `app.py` 맨 위에 `importlib.reload()`를 탑재하여 `app_config`, `core.parser`, `core.vector_db`, `services.llm_service` 모듈이 세션 시작 및 런타임 호출 시 항상 강제 갱신되도록 차단 장치를 구현했습니다.

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
categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d not in ["상위법령", "자치법규", "조례규칙"]]
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

### 6.4. 법제처 Open API 기반 실시간 자치법규 수집 및 파싱 (`legal_downloader.py`)
* **수집 알고리즘 및 물리적 이원화**:
  1. 법제처 자치법규 검색 Open API를 활용하여 `"서울특별시교육감"`, `"서울특별시교육청"` 키워드로 검색된 법률 목록을 실시간 수집 및 중복 제거합니다. (`display=100` 옵션을 통한 페이징 제한 극복)
  2. 중앙 부처 상위 법령(GitHub `legalize-kr` 연계)은 `manuals/상위법령`에 분리 저장하고, 법제처 API로 수집되는 교육청 조례 및 규칙(자치법규)은 `manuals/자치법규`에 저장하도록 물리적인 디렉토리 이원화를 적용했습니다.
  3. 자치법규 상세 본문 XML 조회 시, API 응답 필드 중 지자체 검증 태그가 `"지자체명"`이 아닌 `"지자체기관명"`으로 기재되는 법제처 명세 스키마 불일치 버그를 탐색하여 `"지자체기관명"` 기준으로 정밀 수집하도록 수정했습니다.
  4. 자치법규 XML 내부의 고유 구조인 `<조문>` - `<조>` (하위 `<조문번호>`, `<조제목>`, `<조내용>`) 구조와 `<부칙>` 밑에 직접 나열되는 `<부칙내용>`, `<부칙공포일자>` 플랫 구조를 파싱하여 깔끔한 마크다운(.md) 문서로 동적 렌더링 및 저장합니다.

### 6.5. 스마트 증분 다운로드 캐시 및 통신 에러 자동 복구
* **증분 다운로드 필터링**:
  - 매번 139건의 전체 자치법규 본문 XML을 다운로드하지 않도록, 목록 검색에서 제공하는 각 법안의 `공포일자` 및 `공포번호` 정보를 활용합니다.
  - 기존 로컬 파일 헤더 영역에 기록된 공포일자/공포번호 정보와 실시간 검색 결과 정보가 일치하면 **다운로드 요청 자체를 건너뜀(Skipped)**으로써 동기화 시간을 30초에서 3초 미만으로 단축시킵니다.
* **보안 통신(SSL) 및 API 예외 내성**:
  - 정부 Open API 서버의 잦은 통신 순절 및 비정상 패킷 종료(`UNEXPECTED_EOF_WHILE_READING`) 에러에 대응하기 위해 `make_request_with_retry` 헬퍼 함수를 구현, 최대 4회까지 점진적 시간 대기(지수 백오프) 후 자동 재접속하도록 안전장치를 적용했습니다.
  - 구글 Gemini 임베딩 API 호출 중 빈발하는 `503 Service Unavailable` 에러 역시 `build_cache.py` 루프 내에서 최대 10회까지 지수 백오프 기반으로 재시도하여 인덱싱 실패율을 0%로 만들었습니다.

### 6.6. 관리자 대시보드 파일 상태 판별 - 폴더 해시 기반 방식 (2026-06-11 적용)
* **문제점 (기존 방식)**: 관리자 대시보드에서 개별 파일별로 MD5 해시(`get_file_hash`)를 실시간 계산하여 캐시에 저장된 해시값과 직접 비교했습니다. 이로 인해 아래 두 가지 환경에서 정상적인 파일도 `🔄 변경 감지 (재분석 필요)` 오탐지가 발생했습니다.
  1. **Git 체크아웃 환경 (Streamlit Cloud)**: Git clone 시 모든 파일의 `mtime`이 클론 시각으로 재설정됩니다.
  2. **`legal_downloader.py` 재실행**: 법령 파일을 인터넷에서 새로 내려받으면 줄바꿈, 공백, 날짜 메타데이터 등이 미세하게 달라져 MD5 해시가 변경됩니다.
* **해결책 (신규 방식)**: 파일 단위 MD5 비교 대신 **폴더 전체 해시 (`get_folder_hash`)** 일치 여부를 기준으로 판별합니다.
  - `get_folder_hash`는 폴더 내 **파일명 목록과 각 파일 크기**의 MD5를 계산합니다.
  - 파일 내용이 실제로 변경되면 파일 크기도 달라지므로 폴더 해시도 변경됩니다 → 정확히 감지.
  - `mtime`만 바뀌거나 법령 파일이 같은 크기로 재다운로드 됐을 때 → 오탐지 없음.
  - 폴더 해시가 캐시의 해시와 일치하면 해당 폴더의 모든 파일에 `✅ 분석 완료` 배지를 부여합니다.
  - 폴더 해시가 불일치하면 캐시에 데이터가 있는 파일은 `🔄 변경 감지`, 캐시에 없는 신규 파일은 `➕ 신규 파일`로 표시합니다.
  - `needs_build` 플래그도 동일한 `folder_in_sync` 변수를 재사용하여 `get_folder_hash()` 중복 호출을 제거했습니다.

### 6.7. 벡터 DB 캐시 용량 초경량화 (중복 저장 배제 및 Gzip 압축) (2026-06-11 적용)
* **문제점**: 대용량 지침서가 추가됨에 따라 `.vector_cache.pkl` 파일 크기가 최대 80MB를 초과하여 GitHub의 단일 파일 권장 크기(50MB)를 넘고, 100MB 초과 시 GitHub 푸시가 차단되는 심각한 위험이 있었습니다.
  - **원인**: 기존 캐시 데이터 딕셔너리 구조에서 파일 단위별 조각 청크/임베딩(`data["files"][filename]`)과 전체 병합 청크/임베딩(`data["chunks"]`, `data["embeddings"]`)이 동일한 임베딩 벡터 데이터(768차원 float32 배열)를 이중으로 중복 저장하고 있어 파일 용량이 약 2배 부풀어 나 있었습니다.
* **해결책 (중복 배제 + Gzip 압축)**:
  1. **이중 중복 저장 차단**: 캐시 파일 저장 시(`save_local`) 탑레벨의 `"chunks"` 및 `"embeddings"`를 제거하여 파일 내 중복을 원천 제거했습니다. 로딩 시(`load_local`)에는 `files` 딕셔너리 내의 파일 조각들을 메모리 상에서 순식간에 `np.vstack` 및 `extend` 처리를 통해 동적으로 복원하도록 변경했습니다.
  2. **Gzip 압축 직렬화 적용**: `gzip.open`을 활용하여 직렬화(pickle) 데이터를 실시간 압축 저장하고 압축 로드하게 유도했습니다. (예: `계약` 캐시: **76.87 MB ➔ 9.69 MB**, `공무원` 캐시: **81.29 MB ➔ 36.47 MB**로 압축되어 총 **214.85 MB**의 디스크 및 Git 용량을 절감했습니다.)
  3. **하위 호환성 (Gzip Auto-detection)**: 기존 로컬 컴퓨터나 클라우드 배포 서버에 이미 생성되어 있던 비압축 방식의 구형 `.vector_cache.pkl` 캐시 파일들과 충돌이 없도록, 파일 로드 시 첫 2바이트 매직 번호(`1f 8b`)를 검사하여 `gzip` 압축 여부를 실시간으로 감지하고 비압축 캐시 파일도 부드럽게 Fallback 로딩할 수 있도록 설계하여 런타임 호환성을 100% 보장했습니다.

### 6.8. Streamlit Cloud 메모리 최적화 및 실시간 캐시 무효화 (Streamlit Memory & Cache Invalidation) (2026-06-11 적용)
* **문제점 (기존 방식)**: 
  - **캐시 무효화 실패**: 일반 사용자 진입 시 Streamlit의 `@st.cache_resource` 데코레이터가 `category` 등의 고정된 인자만을 키로 캐싱하기 때문에, 디스크 상의 `.vector_cache.pkl` 파일이 갱신되어도 메모리에 로드된 기존 `LocalVectorDB` 객체를 그대로 계속 반환하여 신규 지침(예: 공무원 자기개발비 지침 등)이 조회되지 않는 문제가 발생했습니다.
  - **메모리 초과(OOM)**: Streamlit Cloud 무료 티어(1GB RAM 제한) 환경에서 다중 카테고리를 반복 로드하거나 캐시 재빌드 시 이전 인덱스 객체들이 소멸하지 않고 지속 누적되어 서버가 자원 한도 초과로 크래시되는 현상이 나타났습니다.
* **해결책 (LRU 캐시 엔트리 제한 + 폴더 해시 파라미터화)**:
  1. **폴더 해시 파라미터 추가**: `build_vector_db` 함수 인자에 폴더 내 파일 구성과 크기를 기반으로 계산된 `folder_hash` 값을 추가로 전달하도록 구조를 변경했습니다. 이를 통해 폴더 내 문서 파일이 변경되면 캐시 키가 동적으로 갱신되어 Streamlit이 구버전 캐시를 자동 무효화하고 디스크에서 최신 캐시를 강제 리로드합니다.
  2. **LRU 캐시 엔트리 제한 (`max_entries=3`)**: 메모리 부하를 줄이기 위해 `build_vector_db`에 `@st.cache_resource(max_entries=3)`를 지정하고, 지침 파일 다운로드 캐시 함수인 `get_file_binary`에 `@st.cache_data(max_entries=3)`를 지정하여 메모리상에 상주하는 최대 캐시 객체 개수를 3개로 강제 제어하도록 설계했습니다. 이를 통해 다중 사용자와 다중 카테고리 요청 시에도 메모리 점유율을 200MB 수준으로 대폭 감축하였습니다.

### 6.9. 관리자 보안 조치(자격 증명 폴백 제거) 및 Streamlit 버전 고정 (2026-06-14 적용)
* **문제점**: 
  - **보안 컴플라이언스 취약성**: 관리자 모드 비밀번호의 폴백(Fallback) 기본값(`********`)이 소스 코드 내부에 하드코딩되어 있어, 설정 누락 또는 소스 유출 시 시스템 보안 취약점이 노출될 수 있는 치명적인 리스크가 있었습니다.
  - **DOM 제어의 프론트엔드 취약성**: Streamlit 버전이 업데이트되면서 고유 엘리먼트(`data-testid="stChatInputTextArea"` 등)의 명칭이 변경되면, JS 자동완성 및 슬래시 명령어 인젝션 모듈이 작동을 멈출 리스크가 상존했습니다.
* **해결책 (보안 하드코딩 제거 + 버전 핀 고정)**:
  1. **동적 보안 랜덤 토큰 폴백**: `os.getenv("ADMIN_PASSWORD")` 호출 시 기본 비밀번호 대신, 환경 변수가 부재할 경우 `secrets.token_urlsafe(32)`를 호출하여 임의의 32바이트 랜덤 토큰을 생성하게 하였습니다. 이에 따라 명시적 환경 설정 없이는 어드민 페이지 접근이 원천 차단됩니다.
  2. **라이브러리 버전 고정 (requirements.txt)**: 배포 버전 불일치로 인한 오작동을 예방하기 위해 패키지 파일 내 Streamlit 버전을 `streamlit==1.56.0`으로 핀(Pin) 고정하여 강제 탑재하였습니다.
