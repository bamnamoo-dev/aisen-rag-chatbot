# 🎨 2026-06-15 UI/UX 프리미엄 리뉴얼 & 버그픽스 패치 내역

본 문서는 2026년 6월 15일에 적용된 **프리미엄 UI/UX 디자인 시스템 전면 리뉴얼**, Streamlit HTML 파싱 버그 수정, DOMPurify 이벤트 핸들러 우회 기술을 상세히 기록합니다.

---

## 1. ⚠️ 주요 해결 과제 및 진단 내용

### ① Streamlit 마크다운 인덴트 코드블록 오파싱 버그

* **원인**: `st.markdown(unsafe_allow_html=True)`에 들여쓰기(4칸 이상)가 있는 멀티라인 f-string HTML을 전달하면, Streamlit이 내부적으로 사용하는 마크다운 파서(mistune/markdown-it)가 해당 블록을 **인덴트 코드블록(indented code block)**으로 분류하여 HTML 태그를 이스케이프 처리 후 텍스트로 출력했습니다.
* **증상**: 참고 카드 HTML(`<div class="ref-card-premium">...`)이 그대로 화면에 텍스트로 노출됨.
* **해결**: 모든 HTML 빌드 f-string을 **단일 라인 문자열 연결(parenthesis 방식)** 으로 전환. 카드/모달/그리드 컨테이너 3종 모두 적용하여 마크다운 파서의 코드블록 판정을 원천 차단함.

```python
# ✅ 수정 후
grid_html = (
    f'<div class="ref-section-premium">'
    f'<div class="ref-grid-premium">{cards_combined}</div>'
    f'</div>'
    f'{modals_combined}'
)
st.markdown(grid_html, unsafe_allow_html=True)
```

---

### ② DOMPurify 이벤트 핸들러(onclick) 자동 제거 버그

* **원인**: Streamlit 프론트엔드 React 레이어는 `unsafe_allow_html=True` 환경에서도 DOMPurify 라이브러리로 HTML을 재정화(sanitize)합니다. DOMPurify의 기본 정책은 `onclick`, `onerror`, `onmouseover` 등 **인라인 이벤트 핸들러 속성을 전부 제거**합니다.
* **증상**: 카드를 클릭해도 모달이 열리지 않음. 닫기 버튼을 눌러도 반응 없음.
* **해결**: 인라인 핸들러 제거 → `data-modal-id` 커스텀 속성 부여 + RAW_JS에 `document.addEventListener('click', ...)` 이벤트 델리게이션 추가.
  * `data-*` 속성은 DOMPurify 허용 목록에 포함되어 있어 제거되지 않음.
  * 이미 `eval(atob(...))` 방식으로 실행 중인 전역 스크립트가 클릭을 감지해 모달을 제어함.
  * 오버레이(배경) 클릭 시 자동 닫기 기능도 함께 구현.

```javascript
// app_config.py RAW_JS — 추가된 이벤트 델리게이션
if (!window.premiumModalBound) {
    window.premiumModalBound = true;
    document.addEventListener('click', function(e) {
        const card = e.target.closest('.ref-card-premium');
        if (card) {
            const mId = card.getAttribute('data-modal-id');
            if (mId) { window.openPremiumModal(mId); return; }
        }
        const closeBtn = e.target.closest('.premium-modal-close-btn');
        if (closeBtn) {
            const mId = closeBtn.getAttribute('data-modal-id');
            if (mId) { window.closePremiumModal(mId); return; }
        }
        if (e.target.classList.contains('premium-modal-overlay')) {
            const mId = e.target.getAttribute('data-modal-id');
            if (mId) { window.closePremiumModal(mId); return; }
        }
    });
}
```

---

## 2. 🎨 UI/UX 프리미엄 리뉴얼 변경 사항

### ① 말풍선(Chat Bubble) 디자인 전면 리뉴얼

| 구분 | 이전 | 이후 |
|:---|:---|:---|
| 사용자 말풍선 | 단순 배경색 | 파란 그라디언트, 슬라이드인 애니메이션 |
| AI 말풍선 | 단순 배경색 | 흰색 카드, AI 아바타 아이콘, 박스 셰도우 |
| 사이드바 | 기본 Streamlit | 글라스모피즘(`backdrop-filter: blur`) 패널 |
| 참고 출처 | `st.popover` 드롭다운 | 프리미엄 카드 그리드 + 글라스모피즘 모달 |
| 입력창 보조 | 없음 | 퀵 카테고리 칩 버튼 |

### ② 참고 카드 그리드 + 글라스모피즘 모달

* **카드 그리드**: 유사도 점수 순서로 정렬된 2~3열 반응형 CSS Grid.
  * 파일 유형별 아이콘 색상: 📄 지침서(노랑), ⚖️ 법령(초록), 🏛️ 조례(파랑).
  * 호버 시 카드 리프트(lift) 효과 및 파란 테두리 하이라이트.
* **글라스모피즘 모달**: 카드 클릭 시 `backdrop-filter: blur(8px)` 오버레이와 함께 scale 진입 애니메이션으로 팝업.
  * 헤더: 파일명 + 유사도 점수 표시.
  * 본문: 원문 텍스트(`max-height: 400px`, 스크롤 지원).
  * 닫기: ×버튼, [확인] 버튼, 배경 클릭 모두 지원.

### ③ 퀵 카테고리 칩 버튼

* 채팅 입력창 상단에 현재 탭에 맞는 카테고리 단축 칩 버튼 렌더링.
* 클릭 시 해당 슬래시 명령어(`/카테고리명`)를 입력창에 자동 주입.

---

## 3. 📂 파일별 변경 사항

### 1) [app.py](file:///g:/내 드라이브/antigravity/sen-chatbot/app.py)
* 참고 카드 HTML: `st.popover` → 프리미엄 카드 그리드 HTML(`ref-card-premium`, `ref-grid-premium`)
* 모달 HTML: 글라스모피즘 팝업 구조(`premium-modal-overlay`, `premium-modal-window`)
* 인라인 `onclick` → `data-modal-id` 속성 전환 (DOMPurify 우회)
* 멀티라인 f-string HTML → 단일 라인 문자열 연결 전환 (마크다운 파싱 오인 방지)
* 퀵 카테고리 칩 버튼 렌더링 로직 추가

### 2) [app_config.py](file:///g:/내 드라이브/antigravity/sen-chatbot/app_config.py)
* `GLOBAL_CSS_STYLE`: 말풍선, 사이드바, 카드 그리드, 모달 프리미엄 CSS 추가
* `RAW_JS`: 퀵 칩 클릭 이벤트 델리게이션 추가
* `RAW_JS`: 참고 카드 + 모달 닫기 이벤트 델리게이션(`premiumModalBound`) 추가
* `RAW_JS`: `openPremiumModal()` / `closePremiumModal()` 전역 함수 추가

### 3) 문서 업데이트
* **[GEMINI.md](file:///g:/내 드라이브/antigravity/sen-chatbot/GEMINI.md)**: 최적화 기술 13, 14번 항목 추가, Last Updated → 2026-06-15
* **[RAG_TECHNICAL_SPEC.md](file:///g:/내 드라이브/antigravity/sen-chatbot/RAG_TECHNICAL_SPEC.md)**: 섹션 7 신규 추가 (UI/UX 프리미엄 리뉴얼 기술 명세)
* **[simple_user_manual.md](file:///g:/내 드라이브/antigravity/sen-chatbot/simple_user_manual.md)**: 참고 카드 설명 → 클릭 모달 방식으로 업데이트

---

## 4. 🧪 기능 테스트 및 검증 결과

* **구문 검사**: `python -m py_compile app.py app_config.py` 컴파일 성공.
* **배포**: `git push origin main` 성공 → Streamlit Cloud 자동 재배포.
* **커밋 이력**:
  * `fc4af1b` — fix: 참고 카드 HTML 인덴트 파싱 버그 수정
  * `4791ee2` — fix: onclick → data-modal-id + JS 이벤트 델리게이션 전환

---

## 5. 🔮 향후 개선 방향

* 모달 내 원문 텍스트의 검색 하이라이트 기능 (Ctrl+F 대체)
* 참고 카드에 PDF 직접 다운로드 버튼 추가
* 카드 클릭 횟수 기반 인기 지침서 랭킹 표시
