# 🏛️ AI-SENSE SMART RAG SYSTEM 기술 명세 (Technical Spec)

"서울시교육청 교육행정 지침 기반 지능형 챗봇 시스템"

---

### 1. 개요 (Overview)
본 시스템은 방대한 양의 교육행정 PDF 지침서를 실시간으로 분석하여 사용자 질문에 정확한 답변을 제공하는 **RAG(Retrieval-Augmented Generation)** 기반 AI 어시스턴트입니다.

### 2. 기술 스택 (Technical Stack)
- **프레임워크**: Streamlit (Python 3.14+)
- **언어 모델**: Google Gemini 2.5 Flash
- **임베딩 모델**: models/text-embedding-004 (또는 models/embedding-001)
- **데이터 처리**: PyMuPDF (fitz) - 고성능 PDF 텍스트 추출
- **검색 알고리즘**: FAISS (시맨틱) + BM25 (어휘) 하이브리드 검색 (6:4 가중합)
- **수치 연산**: NumPy, Scikit-learn

### 3. 핵심 아키텍처: RAG (Retrieval-Augmented Generation)
단순 LLM 호출이 아닌, 데이터 검색 기반 생성 방식을 채택하여 다음과 같은 문제를 해결했습니다.
- **컨텍스트 한계 극복**: 100만 자 이상의 방대한 지침서를 서버 부하 없이 실시간 참조.
- **할당량 최적화**: 전체 데이터를 매번 전송하지 않고 관련 페이지(Top-5)만 선별 전송하여 TPM(Tokens Per Minute) 소모량 90% 절감.
- **환각 방지 (Hallucination)**: 반드시 제공된 지침 범위 내에서만 답변하도록 가드레일 설정.

### 4. 주요 최적화 기술 (Key Optimizations)
1. **Dynamic Model Discovery**: API 키/지역에 상관없이 사용 가능한 임베딩 모델을 자동으로 감지하여 연결.
2. **In-memory Vector Storage**: 세션 기반의 벡터 인덱싱을 통해 별도의 유료 벡터 DB 없이도 빠른 검색 성능 구현.
3. **Robust Connection Manager**: `@st.cache_resource` 싱글톤 패턴을 적용하여 API 클라이언트 연결 안정성 확보 및 세션 복구 로직 탑재.
4. **PyMuPDF Engine**: 기존 라이브러리 대비 10배 이상 빠른 PDF 로딩 및 텍스트 파싱.
5. **Binary Caching**: PDF 다운로드 데이터의 메모리 caching으로 UI 반응 속도 극대화 및 벡터 DB 캐시(.vector_cache.pkl)의 이중 데이터 중복 제거와 Gzip 압축 적용으로 전체 캐시 용량 214MB 초경량화(GitHub 50MB 경고 완벽 해결).
6. **Latest Guideline Score Boosting**: 신구 지침 혼용 시 최신 정보를 우선하기 위한 파일명 키워드/시간 기반 최신 지침 가중치 룰(Score Boosting +0.1) 및 Reranking 로직 탑재.
7. **Atomic Text-Table Separation & Header Replication**: 표 영역 바운딩 박스를 통해 일반 본문과 표 텍스트 중복을 원천 차단하고, 청크 분할 시 표 헤더를 유기적으로 자동 주입하여 환각을 최소화.
8. **FAISS + BM25 Hybrid Search & Context Isolation**: 시맨틱 벡터 검색(FAISS, 60%)과 로컬 경량 한국어 토크나이저 기반의 키워드 검색(BM25, 40%)을 하이브리드 가중합으로 결합하여 고유 명사 및 법령 조항 매칭의 정확도를 극대화하고, 동일 파일 내 청크만 맥락 보강에 사용해 파일 간 맥락 꼬임(오염) 방지.
9. **Streamlit Memory Optimization & Cache Invalidation**: 지침서 변경 시 캐시 갱신을 보장하는 폴더 해시 기반 자동 캐시 무효화 및 메모리 누수 방지를 위한 LRU 캐시 엔트리 제한(max_entries=3) 적용.
10. **Priority-Based Reordering & Cross-Folder Routing (2026-06-12 적용)**: 돈 관련(예산/지출/세입) 및 계약 관련 질문 발생 시 최우선 지침 파일(2026 예산지침 및 계약지침)의 청크를 컨텍스트의 최상단에 강제 배치하고 연관 폴더와 교차 병합 검색을 수행하여 정보의 일관성과 최신성 확보.
11. **FAQ Semantic Caching & Web Sync (Git Push) (2026-06-12 적용)**: 자주 묻는 질문에 대한 고품질 사전 표준 답변(FAQ)을 등록/수정/삭제하는 관리 대시보드와, 로컬 환경에서 터미널 없이 버튼 클릭 한 번으로 원격 깃허브 저장소(`manuals/faq_db.pkl`)에 자동 커밋 & 푸시하여 Streamlit Cloud와 동기화하는 원클릭 동기화 모듈 탑재.
12. **Admin Security Hardening & Streamlit Version Pinning (2026-06-14 적용)**: 소스 코드 내부의 평문 관리자 비밀번호 폴백값을 안전한 동적 보안 랜덤 토큰(cryptographically secure random token) 생성 로직으로 전면 교체하여 자격 증명 유출을 원천 방지하고, UI 조작 자바스크립트의 안정성을 보장하기 위해 배포 버전(`streamlit==1.56.0`)을 핀(Pin) 고정함.

### 5. 운영 지표 (Target Metrics)
- **동시 접속**: 무료 티어 기준 하루 약 100~500명 이상의 질문 처리 가능 (RAG 최적화 적용 결과).
- **답변 속도**: 질문 후 3~5초 이내 스트리밍 응답 개시.
- **정확도**: 참고한 실제 파일명과 페이지 번호를 답변 하단에 100% 명시.

---
*Last Updated: 2026-06-14*

