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
- **검색 알고리즘**: Cosine Similarity (Vector Search)
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
5. **Binary Caching**: PDF 다운로드 데이터의 메모리 캐싱으로 UI 반응 속도 극대화.

### 5. 운영 지표 (Target Metrics)
- **동시 접속**: 무료 티어 기준 하루 약 100~500명 이상의 질문 처리 가능 (RAG 최적화 적용 결과).
- **답변 속도**: 질문 후 3~5초 이내 스트리밍 응답 개시.
- **정확도**: 참고한 실제 파일명과 페이지 번호를 답변 하단에 100% 명시.

---
*Last Updated: 2026-05-16*
