# config.py
# 전역 설정, CSS 디자인 상수, 모델 우선순위 리스트 및 프롬프트 템플릿 관리

# 1. 모델 가용성 우선순위
GEMINI_PRIORITY = [
    "gemini-3.1-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

# 2. RAG 시스템 프롬프트 템플릿
def get_system_prompt(selected_category, context_text):
    return f"""
        당신은 서울특별시교육청의 '{selected_category}' 분야 교육행정 전문가입니다. 
        사용자의 질문에 대해 제공된 [참고 지침 내용]을 바탕으로 **전문적이고 유기적인 해설**을 제공하세요.

        [🌟 답변 작성 구조 규칙]
        1. 💡 핵심 요약 (3대 지침 요점):
           답변의 맨 처음에, 질문과 가장 밀접한 연관성을 가진 상위 3개 참고 지침 내용의 핵심 요점을 한 줄씩(총 3줄 내외) 명확하게 요약하여 번호 매김 형식(1., 2., 3.)으로 제시하세요.
        2. 🔍 상세 해설 및 분석:
           핵심 요약 이후, 본문에서 여러 지침을 종합적이고 유기적으로 연결하여 상세히 해설해 주세요.

        [🌟 답변 스타일: 유기적이고 폭넓은 해설]
        1. 종합적 분석: 여러 파일에서 검색된 정보들을 서로 연결하여, 사용자 업무의 전체 맥락을 이해할 수 있도록 통합적으로 답변하세요.
        2. 해설형 서술: 단순히 지침을 복사해서 나열하지 말고, "이 지침에 따르면 ~하며, 관련하여 ~한 절차가 필요합니다"와 같이 자연스럽게 해설해 주세요.
        3. 풍부한 내용: 질문과 직접 관련된 내용뿐만 아니라, 사용자가 함께 알아두면 좋은 유의사항이나 관련 법령의 취지도 제공된 근거 내에서 최대한 폭넓게 다루세요.
        4. 체계적 구성: 가독성을 위해 개조식(번호, 불렛)을 활용하되, 각 항목 간의 연결 관계가 명확히 드러나도록 문장을 구성하세요.

        [⚠️ 필수 가드레일]
        - 반드시 제공된 [참고 지침 내용] 내의 정보만 사용하세요. (외부 지식 혼합 금지)
        - **예산 과목(원가통계비목)이 다르게 규정된 지침들을 혼동하지 마십시오.** 특정 예산 과목(예: 업무추진비)에서 개인적인 용도의 지출이 금지되더라도, 다른 예산 과목(예: 교직원복지비)에서 해당 경비(예: 교직원 생일기념 경비 1인당 3만원 이내)가 명시적으로 허용된다면, 각 과목별 기준을 정확히 구분하여 안내하여야 합니다. 지침에서 특정 과목으로 지원이 가능하다고 명시한 경우 이를 "허용되지 않는다"라고 일반화하여 오답을 생성해서는 안 됩니다.
        - 만약 제공된 컨텍스트 간에 행정 절차나 기준이 충돌하는 경우, 스코어가 보정되어 상위에 배치된 최신 연도 지침서의 내용을 절대적 기준으로 삼아 답변을 생성하라.
        - 답변의 주요 단락마다 참고한 [파일명 - 페이지]를 소괄호()로 표기하여 신뢰성을 높이세요.
        - 만약 [참고 지침 내용]에 검색 결과가 존재하지 않는다는 안내가 있다면, 억지로 지침을 상상하지 말고 "질문하신 내용에 대한 공식 지침서 근거를 찾지 못했습니다"라고 솔직하게 안내하고, 다른 키워드로 질문을 수정하거나 다른 카테고리를 확인하도록 친절하게 조언해 주세요.

        [참고 지침 내용]
        {context_text}

        ---
        사용자가 업무의 흐름을 한눈에 파악할 수 있도록 상세하고 유기적으로 답변을 작성하세요.
        답변 마지막에는 반드시 아래 형식으로 다음 질문 3개를 추천하세요:
        추천 질문: [질문1], [질문2], [질문3]
        """

def get_legal_system_prompt(selected_category, context_text):
    return f"""
        당신은 서울특별시교육청의 '{selected_category}' 관련 법령 및 자치법규(조례, 규칙) 전문 AI 어시스턴트입니다.
        사용자의 질문에 대해 제공된 [참고 법령/조례 원문]을 바탕으로 **전문적이고 엄격한 법률적 해설**을 제공하세요.

        [🌟 답변 작성 구조 규칙]
        1. 💡 핵심 요약 (3대 법령 요점):
           답변의 맨 처음에, 질문과 가장 밀접한 연관성을 가진 상위 3개 법령/조례 조항의 핵심 내용을 한 줄씩(총 3줄 내외) 번호 매김 형식(1., 2., 3.)으로 요약하여 명확하게 제시하세요.
        2. 🔍 상세 법률 해설 및 조문 매핑:
           본문에서는 근거 법조문을 체계적으로 분류하여 해설해 주세요. "지방공무원법 제X조 제Y항에 따라 ~이며"와 같이 구체적인 조항 번호를 명확하게 표기하여 서술하세요.

        [🌟 답변 스타일: 엄격하고 신뢰성 있는 해설]
        1. 법적 근거 명시: 자의적인 유추 해석이나 상상을 배제하고, 반드시 제공된 조문 텍스트에 근거한 내용만 서술하세요.
        2. 공직 실무 관점: 해당 법령이 공직 및 교육행정 현장에 어떻게 적용되는지, 필요한 요건과 절차를 명확하게 짚어주세요.
        3. 체계적인 개조식: 복잡한 법적 의무나 권리 관계는 불렛포인트나 번호를 활용해 가독성 있게 정리해 주세요.

        [⚠️ 필수 가드레일]
        - 반드시 제공된 [참고 법령/조례 원문]의 내용만 근거로 사용하세요. 외부의 지식을 마음대로 섞어 지어내지 마세요.
        - **예산 과목(원가통계비목)이 다르게 규정된 지침들을 혼동하지 마십시오.** 특정 예산 과목(예: 업무추진비)에서 개인적인 용도의 지출이 금지되더라도, 다른 예산 과목(예: 교직원복지비)에서 해당 경비(예: 교직원 생일기념 경비 1인당 3만원 이내)가 명시적으로 허용된다면, 각 과목별 기준을 정확히 구분하여 안내하여야 합니다. 지침에서 특정 과목으로 지원이 가능하다고 명시한 경우 이를 "허용되지 않는다"라고 일반화하여 오답을 생성해서는 안 됩니다.
        - 만약 제공된 컨텍스트 간에 행정 절차나 기준이 충돌하는 경우, 스코어가 보정되어 상위에 배치된 최신 연도 지침서의 내용을 절대적 기준으로 삼아 답변을 생성하라.
        - 답변의 주요 구절마다 참고한 법령 파일명(예: `지방공무원법.md`)을 소괄호()로 반드시 명시하세요.
        - 일치하는 근거가 전혀 발견되지 않는 경우, "질문하신 내용에 대한 서울시교육청 관련 조례 및 법령 근거를 찾지 못했습니다"라고 정중하게 안내하십시오.

        [참고 법령/조례 원문]
        {context_text}

        ---
        사용자가 조례와 법령의 취지를 정확히 파악할 수 있도록 상세히 답변을 작성하세요.
        답변 마지막에는 반드시 아래 형식으로 다음 질문 3개를 추천하세요:
        추천 질문: [질문1], [질문2], [질문3]
        """

# 3. 카테고리별 동적 이모지 헬퍼 함수
def get_category_emoji(cat_name):
    cat_lower = cat_name.lower()
    if "공지" in cat_lower or "알림" in cat_lower: return "📢"
    elif "공유" in cat_lower or "협조" in cat_lower: return "🔗"
    elif "자유" in cat_lower or "게시판" in cat_lower: return "💬"
    elif "질의" in cat_lower or "응답" in cat_lower or "Q" in cat_lower or "질문" in cat_lower: return "❓"
    elif "계약" in cat_lower or "지출" in cat_lower or "업무" in cat_lower or "재정" in cat_lower: return "💼"
    elif "급식" in cat_lower or "보건" in cat_lower: return "🍏"
    elif "시설" in cat_lower or "재산" in cat_lower or "환경" in cat_lower: return "🏢"
    elif "인사" in cat_lower or "여무" in cat_lower or "복무" in cat_lower: return "👤"
    elif "자료" in cat_lower or "행정" in cat_lower: return "🏛️"
    return "📁"

# 4. Streamlit 글로벌 CSS 스타일
GLOBAL_CSS = """
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    * { font-family: 'Pretendard', sans-serif; }
    .main-title { font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-bottom: 0.5rem; }
    /* 헤더 캡슐 알약 필 (aisen.store 스타일) */
    .header-pill {
        background-color: #eff6ff !important;
        color: #1e60ff !important;
        padding: 4px 12px !important;
        border-radius: 30px !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        display: inline-block !important;
        margin-bottom: 0.75rem !important;
        text-transform: uppercase !important;
    }
    /* 사이드바 컨테이너 스타일 (완전 화이트 & 연한 회색 보더 & 상단 여백 축소) */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #f1f5f9 !important;
    }
    [data-testid="stSidebarUserContent"] {
        padding-top: 0.5rem !important; /* 상단 공백 최소화 */
        padding-bottom: 0.5rem !important;
    }
    /* 사이드바 내부의 모든 버튼 및 내부 자식 요소 강제 좌측 정렬 */
    [data-testid="stSidebar"] button {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
    }
    /* 사이드바 텍스트 줄바꿈 방지(nowrap) 및 말줄임표(ellipsis) 강제 적용 */
    [data-testid="stSidebar"] button p,
    [data-testid="stSidebar"] button span,
    [data-testid="stSidebar"] button div[data-testid="stMarkdownContainer"] p {
        width: 100% !important;
        text-align: left !important;
        display: block !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
        margin: 0 !important;
    }
    /* 사이드바 내부 엘리먼트 간의 Streamlit 기본 외부 간격 조정 */
    [data-testid="stSidebar"] [data-testid="element-container"] {
        margin-bottom: 8px !important; /* 세로 간격 미세 조정 */
        padding-bottom: 0px !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 8px !important; /* 위아래 간격 미세 조정 */
    }
    /* 사이드바 내부 2열 격자의 가로 간격 축소 */
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        gap: 4px !important; /* 기본 16px에서 4px로 축소하여 가로 간격 좁힘 */
    }
    /* 글로벌 프라이머리 버튼 (본문 영역 포함 - 대화용 등) */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e60ff 0%, #0d47a1 100%) !important;
        border-color: #1e60ff !important;
        color: white !important;
        box-shadow: 0 4px 14px rgba(30, 96, 255, 0.2) !important;
        font-weight: 700 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #0a3680 100%) !important;
        border-color: #1d4ed8 !important;
        box-shadow: 0 6px 20px rgba(30, 96, 255, 0.28) !important;
    }
    /* 사이드바 개별 버튼 및 카테고리 카드 디자인 (설명서 카드 테마 매칭) */
    [data-testid="stSidebar"] .stButton > button {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        padding: 6px 8px !important; /* 패딩 대폭 축소하여 한줄 노출 최적화 */
        border-radius: 8px !important; /* 약간 줄여 더 콤팩트하게 */
        font-size: 0.78rem !important; /* 폰트 크기 줄임 */
        margin-bottom: 8px !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-weight: 500 !important;
        border: 1px solid #e2e8f0 !important;
        background-color: #ffffff !important;
        color: #475569 !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02) !important;
    }
    /* 사이드바 버튼 마우스 호버 효과 */
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: #1e60ff !important;
        color: #1e60ff !important;
        background-color: #eff6ff !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(30, 96, 255, 0.08) !important;
    }
    /* 사이드바 내 활성화된 버튼 (kind = primary) 스타일 */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e60ff 0%, #0d47a1 100%) !important;
        color: #ffffff !important;
        border: 1px solid #1e60ff !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(30, 96, 255, 0.2) !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #0a3680 100%) !important;
        color: #ffffff !important;
        border-color: #1d4ed8 !important;
        box-shadow: 0 6px 20px rgba(30, 96, 255, 0.28) !important;
    }
    /* ⭐ 자동 분류 버튼 오렌지색 전용 스타일 */
    .auto-routing-btn-container button[kind="primary"] {
        background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%) !important;
        color: #ffffff !important;
        border: 1px solid #ea580c !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(234, 88, 12, 0.25) !important;
    }
    .auto-routing-btn-container button[kind="primary"]:hover {
        background: linear-gradient(135deg, #f97316 0%, #ea580c 100%) !important;
        border-color: #f97316 !important;
        box-shadow: 0 6px 20px rgba(234, 88, 12, 0.35) !important;
    }
    .auto-routing-btn-container button[kind="secondary"] {
        background-color: #fff7ed !important;
        color: #ea580c !important;
        border: 1px solid #ffedd5 !important;
        box-shadow: 0 1px 2px rgba(234, 88, 12, 0.05) !important;
    }
    .auto-routing-btn-container button[kind="secondary"]:hover {
        border-color: #ff925c !important;
        color: #ff5200 !important;
        background-color: #ffedd5 !important;
        box-shadow: 0 4px 12px rgba(255, 82, 0, 0.1) !important;
    }
    /* 지침서 다운로드 박스 프리미엄 스타일 */
    .file-container {
        background-color: #f0fdf4 !important;
        border-radius: 12px !important;
        padding: 12px !important;
        margin-top: 4px !important;
        margin-bottom: 20px !important;
        border: 1px solid #bbf7d0 !important;
        border-left: 4px solid #16a34a !important;
        box-shadow: 0 2px 8px rgba(22, 163, 74, 0.04) !important;
    }
    .file-container .stDownloadButton > button {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        background-color: #ffffff !important;
        color: #166534 !important;
        border: 1px solid #dcfce7 !important;
        border-radius: 8px !important;
        padding: 6px 10px !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    /* 다운로드 버튼 내부 텍스트 완전 좌측 정렬 강제 및 넘치는 파일명 자동 말줄임(Ellipsis) 적용 */
    .file-container .stDownloadButton > button div[data-testid="stMarkdownContainer"],
    .file-container .stDownloadButton > button p,
    .file-container .stDownloadButton > button span {
        width: 100% !important;
        text-align: left !important;
        display: inline-block !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
        vertical-align: middle !important;
        margin: 0 !important;
    }
    .file-container .stDownloadButton > button:hover {
        background-color: #f0fdf4 !important;
        border-color: #bbf7d0 !important;
        color: #14532d !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03) !important;
    }
    /* 설명서 다운로드 박스 프리미엄 스타일 */
    .manual-container {
        background-color: #eff6ff !important;
        border-radius: 12px !important;
        padding: 8px 10px !important; /* 패딩 대폭 축소 */
        margin-top: 2px !important;    /* 마진 축소 */
        margin-bottom: 8px !important; /* 마진 축소 */
        border: 1px solid #bfdbfe !important;
        border-left: 4px solid #1e60ff !important;
        box-shadow: 0 2px 8px rgba(30, 96, 255, 0.04) !important;
    }
    /* 설명서 내부 보기 버튼 스타일 개별 오버라이드 */
    .manual-container .stButton > button {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        background-color: #ffffff !important;
        color: #1e60ff !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 8px !important;
        padding: 6px 10px !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    .manual-container .stButton > button div[data-testid="stMarkdownContainer"],
    .manual-container .stButton > button p,
    .manual-container .stButton > button span {
        width: 100% !important;
        text-align: left !important;
        display: inline-block !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
        vertical-align: middle !important;
        margin: 0 !important;
    }
    .manual-container .stButton > button:hover {
        background-color: #eff6ff !important;
        border-color: #bfdbfe !important;
        color: #1d4ed8 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03) !important;
    }
    /* 보기 활성화 상태 스타일 */
    .manual-container .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e60ff 0%, #0d47a1 100%) !important;
        color: #ffffff !important;
        border-color: #1e60ff !important;
        box-shadow: 0 4px 10px rgba(30, 96, 255, 0.15) !important;
    }
    /* 대화 카드형 스타일 및 Pretendard 최적화 */
    [data-testid="stChatMessage"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 16px !important;
        padding: 24px 28px !important;
        margin-bottom: 18px !important;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.02), 0 1px 3px rgba(15, 23, 42, 0.01) !important;
        transition: all 0.25s ease !important;
    }
    [data-testid="stChatMessage"]:hover {
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.02) !important;
        border-color: rgba(30, 96, 255, 0.2) !important;
    }
    /* 추천 질문 카드 스타일 - 아이센스토어 시그니처 코발트 블루 매칭 */
    .rec-btn-container .stButton > button {
        background-color: #ffffff !important;
        color: #1e60ff !important;
        border: 1.5px solid #1e60ff !important;
        border-radius: 12px !important;
        padding: 10px 14px !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 2px 4px rgba(30, 96, 255, 0.03) !important;
        height: auto !important;
        width: 100% !important;
        text-align: center !important;
        display: block !important;
    }
    .rec-btn-container .stButton > button:hover {
        background-color: #1e60ff !important;
        color: #ffffff !important;
        border-color: #1e60ff !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px rgba(30, 96, 255, 0.2) !important;
    }
    /* stChatInput 스타일 커스텀 */
    [data-testid="stChatInput"] {
        border-radius: 16px !important;
        border: 5px solid #e2e8f0 !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
        background-color: #ffffff !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
    }
    [data-testid="stChatInput"] textarea {
        font-size: 0.95rem !important;
        color: #0f172a !important;
    }
    /* 포커스 및 모드별 보더 컬러 동적 스타일링 */
    [data-testid="stChatInput"].mode-orange,
    [data-testid="stChatInput"].mode-orange:focus-within {
        border-color: #ea580c !important;
        box-shadow: 0 4px 20px rgba(234, 88, 12, 0.06), 0 0 0 2px rgba(234, 88, 12, 0.15) !important;
    }
    [data-testid="stChatInput"].mode-green,
    [data-testid="stChatInput"].mode-green:focus-within {
        border-color: #16a34a !important;
        box-shadow: 0 4px 20px rgba(22, 163, 74, 0.06), 0 0 0 2px rgba(22, 163, 74, 0.15) !important;
    }
    [data-testid="stChatInput"].mode-blue,
    [data-testid="stChatInput"].mode-blue:focus-within {
        border-color: #1e60ff !important;
        box-shadow: 0 4px 20px rgba(30, 96, 255, 0.06), 0 0 0 2px rgba(30, 96, 255, 0.15) !important;
    }
    /* Autocomplete Dropdown styling */
    #autocomplete-dropdown {
        position: absolute;
        bottom: calc(100% + 5px);
        left: 10px;
        width: 320px;
        max-height: 250px;
        overflow-y: auto;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
        z-index: 999999;
        display: none;
        padding: 6px 0;
    }
    .autocomplete-item {
        padding: 8px 16px;
        cursor: pointer;
        font-size: 0.9rem;
        color: #334155;
        font-weight: 500;
        transition: background-color 0.15s ease, color 0.15s ease;
        display: flex;
        justify-content: space-between;
        align-items: center;
        text-align: left !important;
    }
    .autocomplete-item.active {
        background-color: #eff6ff;
        color: #1e60ff;
        font-weight: 700;
    }
    .autocomplete-item:hover {
        background-color: #f8fafc;
    }
    .autocomplete-item .shortcut {
        font-size: 0.75rem;
        color: #94a3b8;
        background-color: #f1f5f9;
        padding: 2px 6px;
        border-radius: 4px;
    }
    </style>
    <svg style="display:none;">
    <script>
    //<![CDATA[
    (function() {
        const categories = [
            { name: '감사', emoji: '📁', shortcut: '/감사' },
            { name: '계약', emoji: '💼', shortcut: '/계약' },
            { name: '공무원', emoji: '👤', shortcut: '/공무원' },
            { name: '공무직', emoji: '👤', shortcut: '/공무직' },
            { name: '기록물', emoji: '📁', shortcut: '/기록물' },
            { name: '늘봄학교', emoji: '🏫', shortcut: '/늘봄학교' },
            { name: '민원', emoji: '💬', shortcut: '/민원' },
            { name: '발전기금', emoji: '💰', shortcut: '/발전기금' },
            { name: '세입', emoji: '💼', shortcut: '/세입' },
            { name: '시설적립금', emoji: '🏢', shortcut: '/시설적립금' },
            { name: '예산', emoji: '💼', shortcut: '/예산' },
            { name: '정보공개', emoji: '📁', shortcut: '/정보공개' },
            { name: '재산', emoji: '🏢', shortcut: '/재산' },
            { name: '지출', emoji: '💼', shortcut: '/지출' },
            { name: '학교운영위원회', emoji: '🏫', shortcut: '/학교운영위원회' },
            { name: '현장체험학습', emoji: '🎒', shortcut: '/현장체험학습' },
            { name: '산업안전보건', emoji: '🍏', shortcut: '/산업안전보건' },
            { name: '상위법령', emoji: '⚖️', shortcut: '/법령' },
            { name: '자치법규', emoji: '🏛️', shortcut: '/자치법규' }
        ];
        const CHOSUNG = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];
        function getChosung(str) {
            let result = '';
            for (let i = 0; i < str.length; i++) {
                const code = str.charCodeAt(i) - 44032;
                if (code >= 0 && code <= 11172) {
                    result += CHOSUNG[Math.floor(code / 588)];
                } else {
                    result += str.charAt(i);
                }
            }
            return result;
        }
        let activeIndex = -1;
        let filteredList = [];
        let lastTextarea = null;
        function getSelectedCategoryFromDOM() {
            let primaryButtons = document.querySelectorAll('[data-testid="stSidebar"] button[kind="primary"]');
            if (primaryButtons.length === 0) {
                primaryButtons = document.querySelectorAll('button[kind="primary"]');
            }
            for (const btn of primaryButtons) {
                const text = (btn.innerText || btn.textContent || '').trim();
                for (const cat of categories) {
                    if (text.includes(cat.name)) {
                        return cat.name;
                    }
                }
            }
            return '⭐ 자동 분류';
        }
        function updateBorderColor(textarea, chatInputContainer) {
            if (!textarea || !chatInputContainer) return;
            const val = textarea.value.trim();
            const firstWord = val.split(' ')[0];
            const isSlashCmd = firstWord.startsWith('/') && firstWord.length > 1;
            const isSlashActive = val.startsWith('/') && !val.includes(' ') && val.length > 0;
            const currentSelectedCat = getSelectedCategoryFromDOM();
            chatInputContainer.classList.remove('mode-orange', 'mode-green', 'mode-blue');
            if (isSlashActive || isSlashCmd) {
                chatInputContainer.classList.add('mode-green');
            } else if (currentSelectedCat === '⭐ 자동 분류') {
                chatInputContainer.classList.add('mode-orange');
            } else {
                chatInputContainer.classList.add('mode-blue');
            }
        }
        function renderDropdown(dropdown, textarea, chatInputContainer, list) {
            filteredList = list;
            dropdown.innerHTML = '';
            if (list.length === 0) {
                hideDropdown(dropdown);
                return;
            }
            list.forEach((item, index) => {
                const itemEl = document.createElement('div');
                itemEl.className = 'autocomplete-item' + (index === activeIndex ? ' active' : '');
                itemEl.innerHTML = '<span>' + item.emoji + ' ' + item.name + '</span><span class="shortcut">' + item.shortcut + '</span>';
                itemEl.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectItem(dropdown, textarea, chatInputContainer, item);
                });
                dropdown.appendChild(itemEl);
            });
            showDropdown(dropdown);
        }
        function showDropdown(dropdown) {
            dropdown.style.display = 'block';
        }
        function hideDropdown(dropdown) {
            if (!dropdown) return;
            dropdown.style.display = 'none';
            activeIndex = -1;
        }
        function selectItem(dropdown, textarea, chatInputContainer, item) {
            const text = textarea.value;
            const lastSlashIdx = text.lastIndexOf('/');
            if (lastSlashIdx !== -1) {
                const before = text.substring(0, lastSlashIdx);
                textarea.value = before + item.shortcut + ' ';
            } else {
                textarea.value = item.shortcut + ' ';
            }
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.focus();
            hideDropdown(dropdown);
            updateBorderColor(textarea, chatInputContainer);
        }
        function updateActiveItem(dropdown) {
            if (!dropdown) return;
            const items = dropdown.querySelectorAll('.autocomplete-item');
            items.forEach((item, index) => {
                if (index === activeIndex) {
                    item.classList.add('active');
                    item.scrollIntoView({ block: 'nearest' });
                } else {
                    item.classList.remove('active');
                }
            });
        }
        if (window.autocompleteInterval) {
            clearInterval(window.autocompleteInterval);
        }
        window.autocompleteInterval = setInterval(() => {
            const textarea = document.querySelector('textarea[data-testid="stChatInputTextArea"]');
            if (!textarea) return;
            const chatInputContainer = textarea.closest('[data-testid="stChatInput"]');
            if (!chatInputContainer) return;
            let dropdown = chatInputContainer.querySelector('#autocomplete-dropdown');
            if (!dropdown) {
                dropdown = document.createElement('div');
                dropdown.id = 'autocomplete-dropdown';
                chatInputContainer.style.position = 'relative';
                chatInputContainer.appendChild(dropdown);
            }
            if (!textarea.dataset.autocompleteBound) {
                textarea.dataset.autocompleteBound = 'true';
                textarea.addEventListener('input', () => {
                    const val = textarea.value;
                    const lastSlashIdx = val.lastIndexOf('/');
                    updateBorderColor(textarea, chatInputContainer);
                    if (lastSlashIdx === -1) {
                        hideDropdown(dropdown);
                        return;
                    }
                    const searchPart = val.substring(lastSlashIdx + 1);
                    if (searchPart.includes(' ')) {
                        hideDropdown(dropdown);
                        return;
                    }
                    if (searchPart === '') {
                        activeIndex = 0;
                        renderDropdown(dropdown, textarea, chatInputContainer, categories);
                        return;
                    }
                    const query = searchPart.toLowerCase();
                    const queryChosung = getChosung(query);
                    const matched = categories.filter(cat => {
                        const nameLower = cat.name.toLowerCase();
                        const nameChosung = getChosung(nameLower);
                        const shortcutClean = cat.shortcut.replace('/', '').toLowerCase();
                        const shortcutChosung = getChosung(shortcutClean);
                        return nameLower.startsWith(query) || 
                               shortcutClean.startsWith(query) ||
                               nameChosung.startsWith(queryChosung) ||
                               shortcutChosung.startsWith(queryChosung);
                    });
                    activeIndex = matched.length > 0 ? 0 : -1;
                    renderDropdown(dropdown, textarea, chatInputContainer, matched);
                });
                textarea.addEventListener('keydown', (e) => {
                    if (dropdown.style.display === 'block') {
                        if (e.key === 'ArrowDown') {
                            e.preventDefault();
                            activeIndex = (activeIndex + 1) % filteredList.length;
                            updateActiveItem(dropdown);
                        } else if (e.key === 'ArrowUp') {
                            e.preventDefault();
                            activeIndex = (activeIndex - 1 + filteredList.length) % filteredList.length;
                            updateActiveItem(dropdown);
                        } else if (e.key === 'Enter') {
                            if (activeIndex >= 0 && activeIndex < filteredList.length) {
                                e.preventDefault();
                                e.stopPropagation();
                                selectItem(dropdown, textarea, chatInputContainer, filteredList[activeIndex]);
                            }
                        } else if (e.key === 'Escape') {
                            hideDropdown(dropdown);
                        }
                    }
                });
                textarea.addEventListener('focus', () => updateBorderColor(textarea, chatInputContainer));
                textarea.addEventListener('blur', () => {
                    setTimeout(() => hideDropdown(dropdown), 200);
                    updateBorderColor(textarea, chatInputContainer);
                });
                updateBorderColor(textarea, chatInputContainer);
            } else {
                updateBorderColor(textarea, chatInputContainer);
            }
        }, 300);
    })();
    //]]>
    </script>
    </svg>
"""
