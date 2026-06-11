import streamlit as st
import os
import re
import time
import urllib.request
import urllib.parse
from dotenv import load_dotenv
from google.genai import types
import google.generativeai as legacy_genai

import importlib
import sys

# 1. 캐시 방지를 위해 모듈 선로드 및 강제 리로드 (Streamlit Cloud 대응)
import app_config
import core.parser
import core.vector_db
import services.llm_service

importlib.reload(app_config)
importlib.reload(core.parser)
importlib.reload(core.vector_db)
importlib.reload(services.llm_service)

# 2. 필요한 함수/상수 임포트
from app_config import get_system_prompt, get_category_emoji, GLOBAL_CSS, get_legal_system_prompt
from core.vector_db import build_vector_db, retrieve_top_chunks, get_file_hash, get_folder_hash
from services.llm_service import get_genai_client, get_generation_model_name

# 환경변수 로드
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("GOOGLE_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    st.stop()

# 세션 상태에 admin_mode 초기화
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False

admin_mode = st.session_state.admin_mode

# 전역 객체 초기화
client = get_genai_client(api_key)
LOCAL_MODEL_NAME = "gemini-embedding-2"

# 실시간 법령 조회 도구 함수 정의 (Gemini가 필요 시 자동 호출)
def get_korean_law_article(law_name: str, file_type: str = "법률") -> str:
    """대한민국 법령(법률, 시행령, 시행규칙)의 최신 원문을 국문으로 실시간 조회합니다.
    
    Args:
        law_name: 조회하고자 하는 법령명 (예: '지방공무원법', '지방자치단체 입찰 및 계약 집행기준')
        file_type: 법령의 종류로 '법률', '시행령', '시행규칙' 중 하나 (기본값: '법률')
    """
    clean_law_name = law_name.replace(" ", "")
    if "지방계약법" in clean_law_name:
        clean_law_name = "지방자치단체를당사자로하는계약에관한법률"
        
    encoded_law = urllib.parse.quote(clean_law_name)
    encoded_file_type = urllib.parse.quote(f"{file_type}.md")
    raw_url = f"https://raw.githubusercontent.com/legalize-kr/legalize-kr/main/kr/{encoded_law}/{encoded_file_type}"
    
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            markdown_content = response.read().decode('utf-8')
        result = markdown_content[:50000]
        st.session_state.last_fetched_law = {
            "law_name": law_name,
            "file_type": file_type,
            "content": result
        }
        return result
    except Exception as e:
        return f"❌ 법령 '{law_name}' ({file_type}) 원문을 가져오는데 실패했습니다: {e}"

# 세션 콜백
def set_pending_prompt(prompt_text):
    st.session_state.pending_prompt = prompt_text

# 세션 초기화
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "지침서"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "legal_messages" not in st.session_state:
    st.session_state.legal_messages = []
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "⭐ 자동 분류"
if "rebuild_trigger" not in st.session_state:
    st.session_state.rebuild_trigger = 0.0 
if "show_manual" not in st.session_state:
    st.session_state.show_manual = False

manuals_root = "manuals"

# 파일 바이너리 로더
@st.cache_data(max_entries=3)
def get_file_binary(file_path, mtime=0.0):
    with open(file_path, "rb") as f: return f.read()

# UI 기본 설정
st.set_page_config(page_title="AI-SENSE SMART RAG", page_icon="🏛️", layout="wide")

# 사이드바 헤더 및 CSS
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.sidebar.markdown("""
    <div style="display: flex; align-items: center; gap: 10px; padding: 4px 0; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9;">
        <div style="background-color: #1e60ff; color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.25rem; box-shadow: 0 4px 10px rgba(30, 96, 255, 0.25);">I</div>
        <div>
            <div style="font-size: 1.1rem; font-weight: 800; color: #0f172a; line-height: 1.1;">아이센스토어</div>
            <div style="font-size: 0.7rem; font-weight: 700; color: #1e60ff; letter-spacing: 0.05em; margin-top: 1px;">ADMIN RAG SYSTEM</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# 2-Tab 네비게이션 상단 배치
tab_col1, tab_col2 = st.sidebar.columns(2)
with tab_col1:
    is_guidelines = st.session_state.current_tab == "지침서"
    btn_type = "primary" if is_guidelines else "secondary"
    if st.button("📋 지침/매뉴얼", key="tab_guidelines", use_container_width=True, type=btn_type):
        st.session_state.current_tab = "지침서"
        st.session_state.selected_category = "⭐ 자동 분류"
        st.session_state.show_manual = False
        st.rerun()
with tab_col2:
    is_laws = st.session_state.current_tab == "법령"
    btn_type = "primary" if is_laws else "secondary"
    if st.button("⚖️ 법령/조례", key="tab_laws", use_container_width=True, type=btn_type):
        st.session_state.current_tab = "법령"
        st.session_state.selected_category = "자치법규"
        st.session_state.show_manual = False
        st.rerun()

# 사용자 설명서 보기 추가
manual_file_path = "simple_user_manual.html"
if os.path.exists(manual_file_path):
    try:
        st.sidebar.markdown("<div class='manual-container'>", unsafe_allow_html=True)
        st.sidebar.markdown("<div style='font-size:0.85rem; font-weight:700; color:#1e60ff; margin-bottom:8px;'>📖 RAG 시스템 사용 설명서</div>", unsafe_allow_html=True)
        
        # 보기 버튼
        btn_type = "primary" if st.session_state.show_manual else "secondary"
        if st.sidebar.button("📖 설명서 화면에 보기", key="btn_show_manual", use_container_width=True, type=btn_type):
            st.session_state.show_manual = not st.session_state.show_manual
            st.session_state.selected_category = None
            st.rerun()
        st.sidebar.markdown("</div>", unsafe_allow_html=True)
    except Exception:
        pass


if admin_mode:
    st.sidebar.markdown("""
        <div style="background-color: #fff1f2; color: #e11d48; border: 1px solid #ffe4e6; border-radius: 10px; padding: 10px 14px; font-size: 0.8rem; font-weight: 700; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 5px rgba(225, 29, 72, 0.03);">
            <span style="color: #e11d48; font-size: 1rem;">⚙️</span> [관리자 모드] 활성화됨
        </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.selected_category:
        if st.sidebar.button("♻️ 현재 카테고리 캐시 재빌드", use_container_width=True):
            cat_to_rebuild = st.session_state.selected_category
            # 1. 물리 파일 제거
            cat_path = os.path.join(manuals_root, cat_to_rebuild)
            cache_file = os.path.join(cat_path, ".vector_cache.pkl")
            if os.path.exists(cache_file):
                try:
                    os.remove(cache_file)
                except Exception as e:
                    st.sidebar.error(f"캐시 파일 삭제 실패: {e}")
            # 2. 전역 캐시 재빌드 트리거 활성화
            st.session_state.rebuild_trigger = time.time()
            st.rerun()

if st.session_state.current_tab == "지침서":
    st.sidebar.markdown("""
        <div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; padding-left: 4px;">ACTIVE CHANNELS</div>
    """, unsafe_allow_html=True)
    
    if not os.path.exists(manuals_root):
        st.sidebar.error("manuals 폴더가 없습니다.")
        st.stop()
        
    # 정렬된 카테고리 로딩 (조례규칙 카테고리는 Tab 2 전용이므로 제외)
    categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d not in ["상위법령", "자치법규", "조례규칙"]]
    categories = sorted(categories_raw, key=lambda x: (1 if "기타" in x else 0, x))
    
    # ⭐ 자동 분류 버튼을 상단에 별도로 배치
    is_auto = st.session_state.selected_category == "⭐ 자동 분류" or st.session_state.selected_category is None
    btn_type_auto = "primary" if is_auto else "secondary"
    st.sidebar.markdown('<div class="auto-routing-btn-container">', unsafe_allow_html=True)
    if st.sidebar.button("⭐ 자동 분류 (전체 질문)", key="btn_auto_routing", use_container_width=True, type=btn_type_auto):
        st.session_state.selected_category = "⭐ 자동 분류"
        st.session_state.messages = []
        if "chat" in st.session_state: del st.session_state.chat
        st.session_state.show_manual = False
        st.rerun()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)
        
    st.sidebar.markdown("<div style='margin-top: 6px; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # 사이드바 - 카테고리 버튼 생성 (2열 격자 배치)
    active_cat_to_show_files = None
    if st.session_state.selected_category != "⭐ 자동 분류":
        active_cat_to_show_files = st.session_state.selected_category
    else:
        chat_history = st.session_state.messages if st.session_state.current_tab == "지침서" else st.session_state.legal_messages
        for msg in reversed(chat_history or []):
            if msg.get("role") == "assistant" and msg.get("routed_category"):
                active_cat_to_show_files = msg["routed_category"]
                break
    for i in range(0, len(categories), 2):
        cols = st.sidebar.columns(2)
        
        # 첫 번째 열
        cat1 = categories[i]
        is_active1 = st.session_state.selected_category == cat1
        if is_active1:
            active_cat_to_show_files = cat1
        emoji1 = get_category_emoji(cat1)
        btn_label1 = f"{emoji1} {cat1}"
        btn_type1 = "primary" if is_active1 else "secondary"
        with cols[0]:
            clicked1 = st.button(btn_label1, key=f"btn_{cat1}", use_container_width=True, type=btn_type1)
            if clicked1:
                if st.session_state.selected_category == cat1:
                    st.session_state.selected_category = None
                else:
                    st.session_state.selected_category = cat1
                    st.session_state.messages = []
                    if "chat" in st.session_state: del st.session_state.chat
                st.session_state.show_manual = False
                st.rerun()
                
        # 두 번째 열
        if i + 1 < len(categories):
            cat2 = categories[i+1]
            is_active2 = st.session_state.selected_category == cat2
            if is_active2:
                active_cat_to_show_files = cat2
            emoji2 = get_category_emoji(cat2)
            btn_label2 = f"{emoji2} {cat2}"
            btn_type2 = "primary" if is_active2 else "secondary"
            with cols[1]:
                clicked2 = st.button(btn_label2, key=f"btn_{cat2}", use_container_width=True, type=btn_type2)
                if clicked2:
                    if st.session_state.selected_category == cat2:
                        st.session_state.selected_category = None
                    else:
                        st.session_state.selected_category = cat2
                        st.session_state.messages = []
                        if "chat" in st.session_state: del st.session_state.chat
                    st.session_state.show_manual = False
                    st.rerun()

    # 활성화된 카테고리의 지침 파일 다운로드 (전체 너비 렌더링)
    if active_cat_to_show_files:
        cat_path = os.path.join(manuals_root, active_cat_to_show_files)
        files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith('.pdf')])
        if files:
            st.sidebar.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            with st.sidebar.container():
                st.markdown("<div class='file-container'>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:0.85rem; font-weight:600; margin-bottom:8px;'>📄 {active_cat_to_show_files} 지침서 다운로드</div>", unsafe_allow_html=True)
                for f in files:
                    f_path = os.path.join(cat_path, f)
                    display_name = f[:-4] if f.lower().endswith('.pdf') else f
                    st.download_button(
                        label=f"⬇️ {display_name}", 
                        data=get_file_binary(f_path, mtime=os.path.getmtime(f_path)), 
                        file_name=f, 
                        key=f"dl_{f}", 
                        use_container_width=True
                    )
                st.markdown("</div>", unsafe_allow_html=True)
else:
    # 법령/조례 모드 사이드바 표시
    st.sidebar.markdown("""
        <div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; padding-left: 4px;">ACTIVE LAWS</div>
    """, unsafe_allow_html=True)
    
    # 상위법령 / 자치법규 선택 버튼 (2열 구조)
    law_cats = ["상위법령", "자치법규"]
    law_col1, law_col2 = st.sidebar.columns(2)
    
    # selected_category 검증 및 세팅 보장
    if st.session_state.selected_category not in law_cats:
        st.session_state.selected_category = "자치법규"
        
    active_law_cat = st.session_state.selected_category
    
    with law_col1:
        is_active_laws = active_law_cat == "상위법령"
        btn_type_laws = "primary" if is_active_laws else "secondary"
        if st.button("⚖️ 상위법령", key="btn_law_cat_laws", use_container_width=True, type=btn_type_laws):
            st.session_state.selected_category = "상위법령"
            st.session_state.legal_messages = []
            if "chat" in st.session_state: del st.session_state.chat
            st.rerun()
            
    with law_col2:
        is_active_ord = active_law_cat == "자치법규"
        btn_type_ord = "primary" if is_active_ord else "secondary"
        if st.button("🏛️ 자치법규", key="btn_law_cat_ord", use_container_width=True, type=btn_type_ord):
            st.session_state.selected_category = "자치법규"
            st.session_state.legal_messages = []
            if "chat" in st.session_state: del st.session_state.chat
            st.rerun()
    
    cat_path = os.path.join(manuals_root, active_law_cat)
    files = []
    if os.path.exists(cat_path):
        files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith(('.pdf', '.md'))])
        
    with st.sidebar.container():
        st.markdown("<div class='file-container'>", unsafe_allow_html=True)
        if files:
            st.markdown(f"<div style='font-size:0.85rem; font-weight:600; margin-bottom:8px;'>📥 {active_law_cat} 문서 다운로드</div>", unsafe_allow_html=True)
            for f in files:
                f_path = os.path.join(cat_path, f)
                display_name = f[:-3] if f.lower().endswith('.md') else f
                display_name = display_name[:-4] if display_name.lower().endswith('.pdf') else display_name
                st.download_button(
                    label=f"⬇️ {display_name}", 
                    data=get_file_binary(f_path, mtime=os.path.getmtime(f_path)), 
                    file_name=f, 
                    key=f"dl_law_{f}", 
                    use_container_width=True
                )
        else:
            st.markdown(f"<div style='font-size:0.8rem; color:#64748b;'>검색 가능한 {active_law_cat} 파일이 로컬 폴더에 없습니다.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# 사이드바 상태 컨테이너 및 면책 조항 정의
sidebar_stats_container = st.sidebar.container()

# 관리자 로그인/로그아웃 섹션
st.sidebar.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
if not st.session_state.admin_mode:
    with st.sidebar.expander("🔑 관리자 로그인", expanded=False):
        admin_pw_input = st.text_input("비밀번호 입력", type="password", key="admin_pw_input")
        if st.button("로그인", use_container_width=True):
            correct_pw = os.getenv("ADMIN_PASSWORD", "@@admin1601")
            if admin_pw_input == correct_pw:
                st.session_state.admin_mode = True
                st.sidebar.success("관리자 인증 성공!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("비밀번호 불일치")
else:
    if st.sidebar.button("🔒 관리자 로그아웃", use_container_width=True):
        st.session_state.admin_mode = False
        st.rerun()

st.sidebar.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
st.sidebar.caption("💡 **안내 및 면책 조항**: 본 서비스는 교육행정 업무 편의를 위한 AI 보조 도구이며 생성된 답변은 법적 효력이 없습니다. 중요 처리는 반드시 공식 공문 및 최종 발행된 법령 원문을 재확인하시기 바랍니다.")

# 메인 렌더링
# ----------------------------------------------------
# 메인 영역 렌더링 분기
# ----------------------------------------------------
selected_category = st.session_state.selected_category

# 사용자가 관리자 로그인 상태인 경우, 상단 탭을 통해 대시보드와 Q&A를 구분
admin_tab_qa, admin_tab_dashboard = None, None
if admin_mode:
    main_tabs = st.tabs(["💬 대화형 Q&A", "⚙️ RAG 관리자 대시보드"])
    admin_tab_qa = main_tabs[0]
    admin_tab_dashboard = main_tabs[1]

# 1. 관리자 모드인 경우 대시보드 뷰 정의
if admin_mode:
    with admin_tab_dashboard:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #475569 0%, #1e293b 100%); color: white; padding: 20px 28px; border-radius: 12px; margin-bottom: 20px; text-align: left;">
                <h2 style="font-size: 1.5rem; font-weight: 800; margin: 0 0 4px 0; color: white;">⚙️ RAG 지침 도서관 관리자 대시보드</h2>
                <p style="font-size: 0.88rem; opacity: 0.9; margin: 0;">신규 지침 분야를 추가하고, PDF 파일을 업로드/삭제 및 증분 인덱싱할 수 있습니다.</p>
            </div>
        """, unsafe_allow_html=True)
        
        # 1-A. 카테고리 추가 섹션
        with st.expander("📁 1. 신규 카테고리(분야) 생성", expanded=False):
            new_cat_name = st.text_input("새 카테고리 폴더명 입력 (예: 복무, 급여)", key="input_new_cat")
            if st.button("신규 카테고리 생성", use_container_width=True):
                if not new_cat_name.strip():
                    st.error("폴더명을 입력해주세요.")
                elif new_cat_name in ["상위법령", "자치법규", "조례규칙"]:
                    st.error("해당 이름은 시스템 예약어이므로 카테고리로 사용할 수 없습니다.")
                else:
                    new_path = os.path.join(manuals_root, new_cat_name.strip())
                    if os.path.exists(new_path):
                        st.warning("이미 존재하는 카테고리 폴더입니다.")
                    else:
                        try:
                            os.makedirs(new_path, exist_ok=True)
                            st.success(f"🎉 카테고리 폴더 생성 완료: manuals/{new_cat_name}")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"폴더 생성 실패: {e}")
                            
        # 1-B. 파일 관리 섹션 (카테고리 선택)
        st.markdown("### 📄 2. 카테고리별 지침서 파일 관리")
        
        # 모든 카테고리 목록 가져오기
        all_cats_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d))]
        special_cats = ["상위법령", "자치법규", "조례규칙"]
        normal_cats = sorted([c for c in all_cats_raw if c not in special_cats], key=lambda x: (1 if "기타" in x else 0, x))
        all_cats = special_cats + normal_cats
        
        if "sb_manage_category" not in st.session_state:
            st.session_state.sb_manage_category = selected_category if (selected_category and selected_category in all_cats) else all_cats[0]

        manage_category = st.selectbox(
            "관리할 지침 카테고리를 선택하세요",
            all_cats,
            key="sb_manage_category"
        )
        
        if manage_category:
            manage_path = os.path.join(manuals_root, manage_category)
            
            # 파일 업로드 기능
            st.markdown(f"#### ➕ '{manage_category}' 에 파일 업로드 (PDF / MD)")
            uploaded_files = st.file_uploader(
                "여기에 PDF 또는 Markdown 파일을 Drag & Drop 하세요. 복수 선택 가능",
                type=["pdf", "md"],
                accept_multiple_files=True,
                key=f"uploader_{manage_category}"
            )
            
            if uploaded_files:
                save_count = 0
                for u_file in uploaded_files:
                    target_file_path = os.path.join(manage_path, u_file.name)
                    try:
                        with open(target_file_path, "wb") as f:
                            f.write(u_file.read())
                        save_count += 1
                    except Exception as e:
                        st.error(f"❌ {u_file.name} 저장 실패: {e}")
                if save_count > 0:
                    st.success(f"🎉 {save_count}개 파일이 '{manage_category}' 폴더에 안전하게 저장되었습니다!")
                    time.sleep(0.5)
                    st.rerun()
                    
            # 파일 삭제 및 목록 테이블
            st.markdown(f"#### 🔍 '{manage_category}' 폴더 내 파일 목록")
            exist_files = sorted([f for f in os.listdir(manage_path) if f.lower().endswith(('.pdf', '.md'))])
            
            # 캐시 상태 정보 확인
            from core.vector_db import get_folder_hash
            cache_file = os.path.join(manage_path, ".vector_cache.pkl")
            has_cache = os.path.exists(cache_file)
            
            cache_info = None
            if has_cache:
                try:
                    import pickle
                    import gzip
                    is_gzipped = False
                    try:
                        with open(cache_file, "rb") as f_test:
                            magic = f_test.read(2)
                            if magic == b'\x1f\x8b':
                                is_gzipped = True
                    except Exception:
                        pass
                    
                    if is_gzipped:
                        with gzip.open(cache_file, "rb") as f:
                            cache_info = pickle.load(f)
                    else:
                        with open(cache_file, "rb") as f:
                            cache_info = pickle.load(f)
                except Exception:
                    pass
            
            # 폴더 전체 해시로 '최신 동기화 완료' 여부 판별 (파일 개별 해시 대신 폴더 해시 사용)
            # 이유: Git 체크아웃/legal_downloader 실행 등으로 개별 파일의 mtime이나 내용이
            # 미세하게 달라져도 폴더 구성(파일명 + 크기) 기반 해시는 변하지 않으므로 신뢰도가 더 높음
            folder_in_sync = False
            if has_cache and exist_files and cache_info:
                _folder_hash = get_folder_hash(manage_path, LOCAL_MODEL_NAME)
                if (cache_info.get("hash") == _folder_hash and
                        cache_info.get("version") == "2.0" and
                        "migrated_v1_backup.pdf" not in cache_info.get("files", {})):
                    folder_in_sync = True
            
            if exist_files:
                for f_name in exist_files:
                    f_path = os.path.join(manage_path, f_name)
                    try:
                        f_size = os.path.getsize(f_path)
                        f_mtime = os.path.getmtime(f_path)
                        f_mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f_mtime))
                    except Exception:
                        continue
                    
                    status_badge = "➕ 신규 파일 (분석 필요)"
                    chunk_count = 0
                    
                    if cache_info and cache_info.get("version") == "2.0":
                        f_cache = cache_info.get("files", {}).get(f_name)
                        if f_cache:
                            chunk_count = len(f_cache.get("chunks", []))
                            if folder_in_sync:
                                # 폴더 해시 일치 → 이 파일도 최신 상태로 확정
                                status_badge = f"✅ 분석 완료 (청크 {chunk_count}개)"
                            elif chunk_count > 0:
                                # 캐시에 데이터는 있으나 폴더 해시 불일치 → 재분석 필요
                                status_badge = "🔄 변경 감지 (재분석 필요)"
                            else:
                                status_badge = "➕ 신규 파일 (분석 필요)"
                    col_file, col_size, col_time, col_status, col_action = st.columns([4, 2, 3, 3, 2])
                    with col_file:
                        st.markdown(f"**{f_name}**")
                    with col_size:
                        st.markdown(f"`{f_size / 1024:.1f} KB`")
                    with col_time:
                        st.markdown(f"<span style='color: #64748b; font-size: 0.85rem;'>{f_mtime_str}</span>", unsafe_allow_html=True)
                    with col_status:
                        if "✅" in status_badge:
                            st.markdown(f"<span style='color: #10b981; font-weight: 700;'>{status_badge}</span>", unsafe_allow_html=True)
                        elif "🔄" in status_badge:
                            st.markdown(f"<span style='color: #f59e0b; font-weight: 700;'>{status_badge}</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<span style='color: #3b82f6; font-weight: 700;'>{status_badge}</span>", unsafe_allow_html=True)
                    with col_action:
                        if st.button("🗑️ 삭제", key=f"del_{manage_category}_{f_name}", type="secondary", use_container_width=True):
                            try:
                                os.remove(f_path)
                                st.warning(f"📄 파일이 디스크에서 삭제되었습니다: {f_name}")
                                st.session_state.rebuild_trigger = time.time()
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"파일 삭제 에러: {e}")
            else:
                st.info("이 카테고리 폴더는 현재 비어있습니다. PDF/MD 파일을 업로드해 주세요.")
                
            # 수동 분석/빌드 단추
            st.markdown("---")
            st.markdown("#### ⚡ 3. 벡터 DB 증분 빌드 및 캐시 생성")
            
            needs_build = not folder_in_sync
            
            if needs_build:
                st.warning("⚠️ 카테고리 내 파일에 변경 사항이 있거나 아직 빌드되지 않았습니다. 분석 빌드가 필요합니다.")
            else:
                st.success("✅ 현재 폴더 내 모든 파일이 최신 빌드 상태입니다. (동기화 완료)")
                
            col_build, col_clear = st.columns(2)
            with col_build:
                if st.button("⚡ 변경/신규 파일 증분 분석 시작", key="btn_run_build", type="primary", use_container_width=True):
                    cat_path_manage = os.path.join(manuals_root, manage_category)
                    current_folder_hash = get_folder_hash(cat_path_manage, LOCAL_MODEL_NAME)
                    with st.spinner(f"'{manage_category}' 분야 지침서 증분 인덱싱 중..."):
                        rebuilt_db = build_vector_db(
                            category=manage_category,
                            manuals_root=manuals_root,
                            admin_mode=True,
                            _client=client,
                            model_name=LOCAL_MODEL_NAME,
                            rebuild_trigger=time.time(),
                            folder_hash=current_folder_hash
                        )
                        if rebuilt_db and rebuilt_db.chunks:
                            st.success(f"🎉 성공적으로 '{manage_category}' 벡터 인덱싱이 빌드/업데이트되었습니다! (총 {len(rebuilt_db.chunks)}개 청크)")
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.error("빌드에 실패했습니다. 파일을 다시 확인해주세요.")
            with col_clear:
                if st.button("♻️ 인덱스 완전 초기화 및 전체 재빌드", key="btn_clear_rebuild", type="secondary", use_container_width=True):
                    if os.path.exists(cache_file):
                        try:
                            os.remove(cache_file)
                        except Exception as e:
                            st.error(f"캐시 삭제 실패: {e}")
                    cat_path_manage = os.path.join(manuals_root, manage_category)
                    current_folder_hash = get_folder_hash(cat_path_manage, LOCAL_MODEL_NAME)
                    with st.spinner(f"'{manage_category}' 지침서 전체 초기화 후 신규 빌드 중..."):
                        rebuilt_db = build_vector_db(
                            category=manage_category,
                            manuals_root=manuals_root,
                            admin_mode=True,
                            _client=client,
                            model_name=LOCAL_MODEL_NAME,
                            rebuild_trigger=time.time(),
                            folder_hash=current_folder_hash
                        )
                        if rebuilt_db and rebuilt_db.chunks:
                            st.success("🎉 인덱스가 정상적으로 전체 재빌드되었습니다!")
                            time.sleep(0.8)
                            st.rerun()

            # 1-C. 피드백 리포트 섹션
            st.markdown("---")
            st.markdown("### 💬 4. 사용자 피드백 및 만족도 리포트")
            
            from core.feedback import FeedbackManager
            feedbacks = FeedbackManager.load_feedbacks(manuals_root)
            
            if feedbacks:
                total_fb = len(feedbacks)
                likes = sum(1 for fb in feedbacks if fb.get("FeedbackType") == "like")
                dislikes = total_fb - likes
                satisfaction_rate = (likes / total_fb) * 100 if total_fb > 0 else 0
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric("총 피드백 수", f"{total_fb}개")
                with col_m2:
                    st.metric("유용함 (👍)", f"{likes}개", delta=f"{likes/total_fb*100:.1f}%" if total_fb > 0 else None)
                with col_m3:
                    st.metric("수정 필요 (👎)", f"{dislikes}개", delta=f"-{dislikes/total_fb*100:.1f}%" if total_fb > 0 else None, delta_color="inverse")
                with col_m4:
                    st.metric("시스템 만족도", f"{satisfaction_rate:.1f}%")
                
                import pandas as pd
                df_fb = pd.DataFrame(feedbacks)
                df_fb = df_fb[["Timestamp", "Category", "Question", "Answer", "FeedbackType", "Comment", "ReferencedFiles"]]
                df_fb.columns = ["작성시간", "카테고리", "사용자 질문", "AI 답변", "피드백", "상세 사유", "참조 지침서"]
                
                st.dataframe(df_fb, use_container_width=True)
                
                csv_data = df_fb.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📥 피드백 전체 기록 엑셀(CSV) 다운로드",
                    data=csv_data,
                    file_name=f"RAG_Feedback_Report_{time.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("ℹ️ 현재 수집된 사용자 피드백 데이터가 없습니다. 챗봇 질문 시 하단에 피드백이 등록되면 여기에 표시됩니다.")

# 2. Q&A 뷰 렌더링 함수 정의
def render_qa_content():
    if st.session_state.show_manual:
        manual_file_path = "simple_user_manual.html"
        if os.path.exists(manual_file_path):
            with open(manual_file_path, "r", encoding="utf-8") as f:
                manual_html = f.read()
            import streamlit.components.v1 as components
            components.html(manual_html, height=950, scrolling=True)
        else:
            st.error("설명서 파일을 찾을 수 없습니다.")
        st.stop()

    if selected_category:
        db = None
        if selected_category != "⭐ 자동 분류":
            cat_path = os.path.join(manuals_root, selected_category)
            current_folder_hash = get_folder_hash(cat_path, LOCAL_MODEL_NAME)
            with st.spinner(f"AI가 '{selected_category}' 지침 도서관을 구축 중입니다..."):
                db = build_vector_db(
                    category=selected_category, 
                    manuals_root=manuals_root, 
                    admin_mode=admin_mode, 
                    _client=client, 
                    model_name=LOCAL_MODEL_NAME,
                    rebuild_trigger=st.session_state.rebuild_trigger,
                    folder_hash=current_folder_hash
                )
            
            if not db.chunks:
                st.markdown(f"""
                    <div style="padding: 100px 0; text-align: center;">
                        <div style="font-size: 4rem; margin-bottom: 20px;">⏳</div>
                        <h3 style="color: #0f172a; font-weight: 800;">지침서 데이터 준비 중</h3>
                        <p style="color: #64748b; font-size: 1.1rem;">'{selected_category}' 분야의 지침서 분석 캐시가 존재하지 않습니다.</p>
                        <p style="color: #94a3b8; font-size: 0.95rem;">관리자 모드를 활성화하여 최초 1회 문서 분석(인덱싱)을 완료해야 대화 기능이 활성화됩니다.</p>
                    </div>
                """, unsafe_allow_html=True)
                st.stop()
                
            sidebar_stats_container.success(f"✅ {len(db.chunks)}개 문단 분석 완료")
        else:
            sidebar_stats_container.info("ℹ️ 질문 입력 시 분야가 자동 판별되어 지침서가 로드됩니다.")
            
        selected_model_name = get_generation_model_name(client)
        sidebar_stats_container.info(f"🚀 AI 엔진: **{selected_model_name.split('/')[-1] if selected_model_name else '자동'}**")
        sidebar_stats_container.divider()

        # 헤더 렌더링 분기
        if st.session_state.current_tab == "지침서":
            header_name = selected_category
            if selected_category == "⭐ 자동 분류":
                header_name = "⭐ 행정 지침 자동 분류 Q&A"
                header_desc = "질문을 입력하시면 AI가 알맞은 분야의 교육청 지침서를 자동으로 탐색하여 최적의 답변을 드립니다."
            else:
                header_desc = "행정지원과의 공식 지침서 분석 및 실시간 답변을 제공합니다."
            st.markdown(f"""
                <div style="background: linear-gradient(135deg, #1e60ff 0%, #0d47a1 100%); color: white; padding: 24px 32px; border-radius: 16px; box-shadow: 0 10px 30px rgba(30, 96, 255, 0.08); margin-bottom: 30px; position: relative; overflow: hidden; text-align: left;">
                    <span style="display: inline-block; background: rgba(255, 255, 255, 0.15); padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 8px; text-transform: uppercase;">LIVE RAG ENGINE SYSTEM</span>
                    <h1 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 6px 0; color: white;">{header_name}</h1>
                    <p style="font-size: 0.9rem; opacity: 0.9; margin: 0; font-weight: 400;">{header_desc}</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            header_title = "⚖️ 국가 상위 법령 검색" if selected_category == "상위법령" else "🏛️ 서울시교육청 자치법규 검색"
            header_desc = "학교 행정의 기준이 되는 주요 중앙 부처 법률·시행령·시행규칙을 검색합니다." if selected_category == "상위법령" else "서울특별시교육청에서 공포한 핵심 조례·시행규칙·규정을 검색합니다."
            st.markdown(f"""
                <div style="background: linear-gradient(135deg, #10b981 0%, #047857 100%); color: white; padding: 24px 32px; border-radius: 16px; box-shadow: 0 10px 30px rgba(16, 185, 129, 0.08); margin-bottom: 30px; position: relative; overflow: hidden; text-align: left;">
                    <span style="display: inline-block; background: rgba(255, 255, 255, 0.15); padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 8px; text-transform: uppercase;">LEGAL SEARCH ENGINE</span>
                    <h1 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 6px 0; color: white;">{header_title}</h1>
                    <p style="font-size: 0.9rem; opacity: 0.9; margin: 0; font-weight: 400;">{header_desc}</p>
                </div>
            """, unsafe_allow_html=True)

        # 선택된 탭에 따른 대화 기록 로드
        chat_history = st.session_state.messages if st.session_state.current_tab == "지침서" else st.session_state.legal_messages

        for idx, message in enumerate(chat_history):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # 자동 분류 결과 안내 메시지 표시
                if message["role"] == "assistant" and message.get("routed_category"):
                    st.markdown(f"""
                        <div style="background-color: #fff7ed; border-left: 4px solid #ea580c; padding: 8px 12px; border-radius: 8px; font-size: 0.82rem; font-weight: 700; color: #c2410c; margin-top: 6px; margin-bottom: 8px; display: inline-block;">
                            📍 자동 분류 결과: <strong>{message['routed_category']}</strong> 분야 지침서 검색
                        </div>
                    """, unsafe_allow_html=True)
                
                # 참조 지침서/법령 팝오버 렌더링
                if message["role"] == "assistant" and message.get("unique_chunks"):
                    unique_chunks = message["unique_chunks"]
                    st.markdown("---")
                    st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>📍 참고 지침 원문 확인</div>" if st.session_state.current_tab == "지침서" else "<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>📍 참고 법령/조례 원문 확인</div>", unsafe_allow_html=True)
                    cols = st.columns(min(len(unique_chunks), 5))
                    for c_idx, chunk in enumerate(unique_chunks):
                        with cols[c_idx % 5]:
                            with st.popover(f"📄 {chunk['metadata'][:12]}...", use_container_width=True):
                                st.markdown(f"**[{chunk['metadata']}] 원문 (유사도: {chunk['score']:.4f})**")
                                st.markdown(f"<div style='background: #f8fafc; padding: 10px; border-radius: 5px; font-size: 0.85rem; border: 1px solid #e2e8f0; max-height: 300px; overflow-y: auto;'>{chunk['content_ui']}</div>", unsafe_allow_html=True)
                                st.markdown("<div style='font-size: 0.7rem; color: #94a3b8; margin-top: 5px;'>※ 위 내용은 추출된 원문입니다.</div>", unsafe_allow_html=True)

                if st.session_state.current_tab == "지침서" and message.get("fetched_law"):
                    law_data = message["fetched_law"]
                    st.markdown("---")
                    st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>⚖️ 상위 근거 법령 원문 확인</div>", unsafe_allow_html=True)
                    with st.popover(f"💡 {law_data['law_name']} ({law_data['file_type']}) 원문 보기", use_container_width=True):
                        st.markdown(f"### {law_data['law_name']} ({law_data['file_type']})")
                        st.markdown(f"<div style='background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 0.85rem; border: 1px solid #e2e8f0; max-height: 400px; overflow-y: auto;'>{law_data['content']}</div>", unsafe_allow_html=True)
                
                # 피드백 수집기 연동
                if message["role"] == "assistant":
                    msg_cat = message.get("routed_category") or selected_category
                    if message.get("feedback"):
                        val = message["feedback"]
                        icon = "👍" if val == "like" else "👎"
                        st.markdown(f"<span style='font-size: 0.75rem; color: #10b981; font-weight: 600;'>{icon} 피드백이 전송되었습니다.</span>", unsafe_allow_html=True)
                    elif idx == len(chat_history) - 1:
                        # 펜딩 상태가 아니면 Thumbs 위젯 표시
                        if not (st.session_state.get("pending_dislike") and st.session_state.pending_dislike["idx"] == idx):
                            feedback_key = f"feedback_{msg_cat}_{idx}"
                            fb_val = st.feedback("thumbs", key=feedback_key)
                            if fb_val is not None:
                                fb_type = "like" if fb_val == 1 else "dislike"
                                if fb_type == "like":
                                    from core.feedback import FeedbackManager
                                    ref_files = message.get("referenced_files", [])
                                    FeedbackManager.save_feedback(
                                        category=msg_cat,
                                        question=chat_history[idx-1]["content"] if idx > 0 else "이전 질문 없음",
                                        answer=message["content"],
                                        feedback_type="like",
                                        referenced_files=ref_files
                                    )
                                    message["feedback"] = "like"
                                    st.toast("👍 소중한 피드백이 전송되었습니다. 감사합니다!", icon="💚")
                                    st.rerun()
                                else:
                                    st.session_state.pending_dislike = {
                                        "idx": idx,
                                        "category": msg_cat,
                                        "question": chat_history[idx-1]["content"] if idx > 0 else "이전 질문 없음",
                                        "answer": message["content"],
                                        "ref_files": message.get("referenced_files", [])
                                    }
                                    st.rerun()
                        
                        # 펜딩 상태인 경우 사유 폼 표시
                        if st.session_state.get("pending_dislike") and st.session_state.pending_dislike["idx"] == idx:
                            with st.form(key=f"dislike_form_{idx}"):
                                comment = st.text_input("구체적인 오류나 수정이 필요한 내용을 적어주세요 (선택):", placeholder="예: 수의계약 개정 한도가 반영되지 않았습니다.")
                                submit_feedback = st.form_submit_button("피드백 제출")
                                if submit_feedback:
                                    from core.feedback import FeedbackManager
                                    p_info = st.session_state.pending_dislike
                                    FeedbackManager.save_feedback(
                                        category=p_info["category"],
                                        question=p_info["question"],
                                        answer=p_info["answer"],
                                        feedback_type="dislike",
                                        comment=comment,
                                        referenced_files=p_info["ref_files"]
                                    )
                                    message["feedback"] = "dislike"
                                    del st.session_state.pending_dislike
                                    st.toast("👎 피드백이 전송되었습니다. 감사 점검에 반영하겠습니다!", icon="✔️")
                                    st.rerun()
                    
                    # 마지막 메시지이면서 추천 질문이 있는 경우 렌더링
                    if idx == len(chat_history) - 1 and message.get("recommendations"):
                        recommendations = message["recommendations"]
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown("<div style='font-size: 0.82rem; font-weight: 700; color: #64748b; margin-bottom: 8px;'>💡 이런 질문은 어떠세요?</div>", unsafe_allow_html=True)
                        rec_cols = st.columns(len(recommendations))
                        for r_idx, rec in enumerate(recommendations):
                            with rec_cols[r_idx]:
                                st.markdown("<div class='rec-btn-container'>", unsafe_allow_html=True)
                                st.button(f"🔍 {rec}", key=f"rec_{r_idx}_{st.session_state.current_tab}_{idx}", on_click=set_pending_prompt, args=(rec,))
                                st.markdown("</div>", unsafe_allow_html=True)

        prompt = None
        if "pending_prompt" in st.session_state:
            prompt = st.session_state.pending_prompt
            del st.session_state.pending_prompt
        else:
            if st.session_state.current_tab == "지침서":
                if selected_category == "⭐ 자동 분류":
                    input_placeholder = "궁금하신 행정 업무에 대해 자유롭게 질문해 주세요. (자동 분류)"
                else:
                    input_placeholder = f"{selected_category} 업무에 대해 질문해 주세요."
            else:
                law_example = "지방공무원법상 직위해제" if selected_category == "상위법령" else "공무원 복무 조례상 특별휴가"
                input_placeholder = f"궁금하신 {selected_category}에 대해 질문해 주세요. (예: {law_example})"
            prompt = st.chat_input(input_placeholder)

        if prompt:
            st.session_state.last_fetched_law = None
            
            if st.session_state.current_tab == "지침서":
                st.session_state.messages.append({"role": "user", "content": prompt})
            else:
                st.session_state.legal_messages.append({"role": "user", "content": prompt})
                
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.status("🔍 질문을 분석하고 관련 지침을 검색하고 있습니다...", expanded=True) as status:
                # Determine actual category and database dynamically if in Auto Routing mode
                actual_category = selected_category
                active_db = db
                routed_category_name = None
                relevant_chunks = []
                
                if selected_category == "⭐ 자동 분류" and st.session_state.current_tab == "지침서":
                    from core.vector_db import route_query_by_keywords
                    categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d not in ["상위법령", "자치법규", "조례규칙"]]
                    categories_list = sorted(categories_raw, key=lambda x: (1 if "기타" in x else 0, x))
                    best_cat = route_query_by_keywords(prompt, categories_list, return_candidates=False)
                else:
                    best_cat = selected_category
                
                # 지출, 세입, 계약 질문은 예산 폴더와 교차 검색 및 병합
                search_categories = [best_cat]
                if best_cat in ["지출", "세입", "계약"] and best_cat != "예산":
                    categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d not in ["상위법령", "자치법규", "조례규칙"]]
                    if "예산" in categories_raw:
                        search_categories.append("예산")
                
                searched_cats = []
                
                # 1단계: 지정된 카테고리들에서 검색 및 병합
                for cat in search_categories:
                    actual_category = cat
                    if selected_category == "⭐ 자동 분류" and st.session_state.current_tab == "지침서" and len(search_categories) > 1:
                        st.write(f"🛰️ 로컬 벡터 DB [{actual_category}] 분야 탐색 중...")
                    else:
                        st.write(f"🛰️ 1. 로컬 벡터 DB에서 관련 지침서 탐색 중..." if st.session_state.current_tab == "지침서" else "🛰️ 1. 로컬 법령 벡터 DB에서 관련 조항 탐색 중...")
                    time.sleep(0.1)
                    
                    cat_path = os.path.join(manuals_root, actual_category)
                    current_folder_hash = get_folder_hash(cat_path, LOCAL_MODEL_NAME)
                    active_db = build_vector_db(
                        category=actual_category, 
                        manuals_root=manuals_root, 
                        admin_mode=admin_mode, 
                        _client=client, 
                        model_name=LOCAL_MODEL_NAME,
                        rebuild_trigger=st.session_state.rebuild_trigger,
                        folder_hash=current_folder_hash
                    )
                    
                    chunks_for_cat = retrieve_top_chunks(prompt, active_db, client, k=15, threshold=0.4, model_name=LOCAL_MODEL_NAME)
                    if len(chunks_for_cat) > 0:
                        relevant_chunks.extend(chunks_for_cat)
                        if actual_category not in searched_cats:
                            searched_cats.append(actual_category)
                
                # 2단계: 만약 1차 분류 폴더들에서 아무 매칭 청크도 안 나온 경우, 전체 폴더에 대해 순차 Fallback 검색 수행
                if len(relevant_chunks) == 0 and selected_category == "⭐ 자동 분류" and st.session_state.current_tab == "지침서":
                    st.write("⚠️ 1차 분류 폴더에서 관련 답변을 찾지 못해, 다른 폴더들을 교차 탐색합니다...")
                    time.sleep(0.3)
                    
                    categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d not in ["상위법령", "자치법규", "조례규칙"]]
                    categories_list = sorted(categories_raw, key=lambda x: (1 if "기타" in x else 0, x))
                    fallback_candidates = [cat for cat in categories_list if cat not in search_categories]
                    
                    for cat in fallback_candidates:
                        actual_category = cat
                        cat_path = os.path.join(manuals_root, actual_category)
                        current_folder_hash = get_folder_hash(cat_path, LOCAL_MODEL_NAME)
                        active_db = build_vector_db(
                            category=actual_category, 
                            manuals_root=manuals_root, 
                            admin_mode=admin_mode, 
                            _client=client, 
                            model_name=LOCAL_MODEL_NAME,
                            rebuild_trigger=st.session_state.rebuild_trigger,
                            folder_hash=current_folder_hash
                        )
                        chunks_for_cat = retrieve_top_chunks(prompt, active_db, client, k=15, threshold=0.4, model_name=LOCAL_MODEL_NAME)
                        if len(chunks_for_cat) > 0:
                            relevant_chunks.extend(chunks_for_cat)
                            searched_cats.append(actual_category)
                            best_cat = actual_category  # UI 및 다운로드 연동용 카테고리 업데이트
                            break
                
                # 3단계: 검색 결과 점수 기준 재정렬 및 UI 메시지 출력
                if len(relevant_chunks) > 0:
                    relevant_chunks = sorted(relevant_chunks, key=lambda x: x["score"], reverse=True)
                    if len(searched_cats) > 1:
                        st.write(f"📊 유사도 기준 필터링 완료 (유사도 0.4 이상 선별된 청크 수: {len(relevant_chunks)}개) - {searched_cats} 폴더 채택 및 교차 병합 완료")
                    else:
                        st.write(f"📊 유사도 기준 필터링 완료 (유사도 0.4 이상 선별된 청크 수: {len(relevant_chunks)}개) - [{best_cat}] 폴더 채택")
                
                actual_category = best_cat
                if selected_category == "⭐ 자동 분류" and st.session_state.current_tab == "지침서":
                    routed_category_name = best_cat
                
                time.sleep(0.2)
                st.write("🤖 3. AI-SENSE 스마트 엔진이 답변을 작성하고 있습니다...")
                status.update(label="🤖 AI가 답변을 작성하고 있습니다...", state="running")

            unique_chunks = []
            seen_contents = set()
            for c in relevant_chunks:
                if c['content_llm'] not in seen_contents:
                    unique_chunks.append(c)
                    seen_contents.add(c['content_llm'])

            if unique_chunks:
                best_score = unique_chunks[0]['score']
                if best_score >= 0.85: unique_chunks = unique_chunks[:3]
                elif best_score >= 0.75: unique_chunks = unique_chunks[:6]
                elif best_score >= 0.60: unique_chunks = unique_chunks[:10]

            if unique_chunks:
                context_text = "\n\n".join([f"[{c['metadata']}] (유사도: {c['score']:.4f})\n{c['content_llm']}" for c in unique_chunks])
            else:
                context_text = "(검색 결과가 존재하지 않습니다. 질문과 일치하거나 유사도가 0.4 이상인 공식 지침서 내용이 전혀 발견되지 않았습니다.)"

            if st.session_state.current_tab == "지침서":
                system_prompt = get_system_prompt(actual_category, context_text)
            else:
                system_prompt = get_legal_system_prompt(actual_category, context_text)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                errors = []
                
                history = []
                target_history = st.session_state.messages if st.session_state.current_tab == "지침서" else st.session_state.legal_messages
                raw_history = target_history[-5:-1] if len(target_history) >= 5 else target_history[:-1]
                if len(raw_history) % 2 != 0: raw_history = raw_history[1:]
                    
                for m in raw_history:
                    role = "user" if m["role"] == "user" else "model"
                    history.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))
                
                try:
                    excluded = []
                    for _ in range(3):
                        gen_model = get_generation_model_name(client, exclude_models=excluded)
                        if not gen_model: break
                        
                        try:
                            tools_config = [get_korean_law_article] if st.session_state.current_tab == "지침서" else None
                            
                            response_stream = client.models.generate_content_stream(
                                model=gen_model,
                                contents=history + [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
                                config=types.GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    temperature=0.3,
                                    max_output_tokens=2048,
                                    tools=tools_config
                                )
                            )
                            def stream_generator():
                                for chunk in response_stream:
                                    if chunk.text: yield chunk.text
                            full_response = message_placeholder.write_stream(stream_generator())
                            break
                        except Exception as model_error:
                            try:
                                legacy_genai.configure(api_key=api_key)
                                legacy_model = legacy_genai.GenerativeModel(
                                    model_name=gen_model.replace("models/", ""),
                                    system_instruction=system_prompt
                                )
                                legacy_response = legacy_model.generate_content(prompt)
                                full_response = legacy_response.text
                                break
                            except Exception as legacy_error:
                                error_msg = f"New SDK: {str(model_error)[:50]} / Legacy: {str(legacy_error)[:50]}"
                                errors.append(f"{gen_model.split('/')[-1]}: {error_msg}")
                                excluded.append(gen_model)
                                continue
                    
                    if not full_response:
                        st.error("사용 가능한 모든 AI 모델의 할당량이 초과되었습니다.")
                        with st.sidebar.expander("🔍 상세 에러 로그"):
                            for err in errors: st.write(err)
                        st.stop()

                    main_response = full_response
                    recommendations = []
                    pattern = r"\**추천\s*질문\**\s*:\s*"
                    match = re.search(pattern, full_response)
                    
                    if match:
                        parts = re.split(pattern, full_response, maxsplit=1)
                        if len(parts) >= 2:
                            main_response = parts[0].strip()
                            rec_str = parts[1].strip()
                            recommendations = [r.strip().strip("[]").strip() for r in rec_str.split(",")]

                    message_placeholder.markdown(main_response)
                    
                    fetched_law = None
                    if st.session_state.current_tab == "지침서" and st.session_state.get("last_fetched_law"):
                        fetched_law = st.session_state.last_fetched_law

                    if st.session_state.current_tab == "지침서":
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": main_response,
                            "fetched_law": fetched_law,
                            "referenced_files": [c['metadata'] for c in unique_chunks] if unique_chunks else [],
                            "unique_chunks": unique_chunks,
                            "recommendations": recommendations,
                            "routed_category": routed_category_name
                        })
                    else:
                        st.session_state.legal_messages.append({
                            "role": "assistant", 
                            "content": main_response,
                            "referenced_files": [c['metadata'] for c in unique_chunks] if unique_chunks else [],
                            "unique_chunks": unique_chunks,
                            "recommendations": recommendations
                        })
                    
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
                    return
                
                st.rerun()
    else:
        st.markdown("""
            <div style="max-width: 900px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.02); border: 1px solid #e2e8f0; overflow: hidden; text-align: left;">
                <div style="background: linear-gradient(135deg, #1e60ff 0%, #0d47a1 100%); color: white; padding: 48px 40px; position: relative; overflow: hidden;">
                    <span style="display: inline-block; background: rgba(255, 255, 255, 0.15); padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 16px; text-transform: uppercase;">ADMIN RAG SYSTEM</span>
                    <h1 style="font-size: 2.2rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 12px; margin-top: 0; color: white;">🏛️ 교육행정 지능형 RAG 시스템</h1>
                    <p style="font-size: 1.05rem; opacity: 0.9; max-width: 680px; font-weight: 400; margin: 0; line-height: 1.55;">수만 페이지의 교육청 지침서 중 필요한 내용을 실시간 검색하여 가장 안전하고 똑똑하게 답변하는 스마트 어시스턴트입니다.</p>
                </div>
                <div style="padding: 40px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div style="border: 1px solid #e2e8f0; padding: 24px; border-radius: 10px; background: #ffffff; transition: all 0.25s ease;">
                            <span style="font-size: 1.8rem; margin-bottom: 12px; display: inline-block;">☁️</span>
                            <h3 style="font-size: 1.05rem; font-weight: 700; margin-top: 0; margin-bottom: 8px; color: #0f172a;">클라우드 인프라 최적화</h3>
                            <p style="font-size: 0.88rem; color: #475569; margin: 0; line-height: 1.55;">외부 유출 우려가 없는 공개 행정 지침 데이터의 특성을 활용, 로컬 FAISS 인덱싱 기술과 구글 Gemini API의 연산력을 결합한 고속·고효율 하이브리드 구조</p>
                        </div>
                        <div style="border: 1px solid #e2e8f0; padding: 24px; border-radius: 10px; background: #ffffff; transition: all 0.25s ease;">
                            <span style="font-size: 1.8rem; margin-bottom: 12px; display: inline-block;">⚡</span>
                            <h3 style="font-size: 1.05rem; font-weight: 700; margin-top: 0; margin-bottom: 8px; color: #0f172a;">초고속 시맨틱 검색</h3>
                            <p style="font-size: 0.88rem; color: #475569; margin: 0; line-height: 1.55;">로컬 코사인 유사도 벡터 검색 기술을 활용해 0.001초 만에 최적의 관련 지침을 선별하고 Reranking 기술로 최신 지침을 우선 노출합니다.</p>
                        </div>
                    </div>
                    <div style="display: flex; gap: 16px; padding: 20px; border-radius: 10px; border-left: 4px solid #3b82f6; font-size: 0.9rem; margin-top: 30px; background-color: #eff6ff; color: #1e40af;">
                        <span style="font-size: 1.25rem; flex-shrink: 0; line-height: 1;">💡</span>
                        <div>
                            <strong>시작 가이드</strong>
                            <p style="margin: 4px 0 0 0; line-height: 1.5;">좌측의 <span style="font-weight: 700; color: #1e60ff;">[ACTIVE CHANNELS]</span> 업무 카드 중 하나를 선택해 대화를 시작해 보세요. 카테고리가 활성화되면 해당 분야의 지침서 다운로드도 제공됩니다.</p>
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

# 3. 탭 존재 유무에 맞춰 렌더링 호출
if admin_mode:
    with admin_tab_qa:
        render_qa_content()
else:
    render_qa_content()
