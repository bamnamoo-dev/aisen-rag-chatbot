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
    
    /* 사이드바 컨테이너 스타일 (완전 화이트 & 연한 회색 보더) */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #f1f5f9 !important;
    }
    
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
    
    /* 사이드바 내부 엘리먼트 간의 Streamlit 기본 외부 간격 극단적으로 축소 */
    [data-testid="stSidebar"] [data-testid="element-container"] {
        margin-bottom: 2px !important;
        padding-bottom: 0px !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 2px !important;
    }

    /* 카테고리 카드 래퍼 공통 스타일 (초압축 간격 및 좌측 정렬) */
    .active-card-container .stButton > button,
    .inactive-card-container .stButton > button {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        padding: 5px 8px !important;
        border-radius: 8px !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        margin-bottom: 2px !important;
        transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    /* 내부 텍스트 완전 좌측 정렬 강제 */
    .active-card-container .stButton > button div[data-testid="stMarkdownContainer"],
    .inactive-card-container .stButton > button div[data-testid="stMarkdownContainer"],
    .active-card-container .stButton > button p,
    .inactive-card-container .stButton > button p {
        width: 100% !important;
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        gap: 6px !important;
        margin: 0 !important;
    }

    /* 비활성 카테고리 카드 (투명 & 플랫 피트) */
    .inactive-card-container .stButton > button {
        background-color: transparent !important;
        color: #475569 !important;
        border: none !important;
        box-shadow: none !important;
    }
    
    .inactive-card-container .stButton > button:hover {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
        transform: translateY(-1px) !important;
    }

    /* 활성 카테고리 카드 (아이센스토어 시그니처 코발트 블루 & 강한 딥 섀도우) */
    .active-card-container .stButton > button {
        background: #1e60ff !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 6px 16px rgba(30, 96, 255, 0.18) !important;
        transform: translateY(-1px) !important;
        font-weight: 700 !important;
    }
    
    .active-card-container .stButton > button:hover {
        background: #1d4ed8 !important;
        color: #ffffff !important;
        box-shadow: 0 8px 20px rgba(30, 96, 255, 0.24) !important;
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
    
    /* 대화 카드형 스타일 및 Pretendard 최적화 */
    [data-testid="stChatMessage"] {
        background-color: #ffffff !important;
        border: 1px solid #f1f5f9 !important;
        border-radius: 20px !important;
        padding: 24px 28px !important;
        margin-bottom: 18px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.015) !important;
        transition: all 0.25s ease !important;
    }
    [data-testid="stChatMessage"]:hover {
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.025) !important;
        border-color: #e2e8f0 !important;
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
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
        background-color: #ffffff !important;
    }
    [data-testid="stChatInput"] textarea {
        font-size: 0.95rem !important;
        color: #0f172a !important;
    }
    </style>
"""
