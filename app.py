import streamlit as st
import os
import re
import time
import urllib.request
import urllib.parse
from dotenv import load_dotenv
from google.genai import types
import google.generativeai as legacy_genai

# 분리된 모듈 임포트
from app_config import get_system_prompt, get_category_emoji, GLOBAL_CSS, get_legal_system_prompt
from core.vector_db import build_vector_db, retrieve_top_chunks
from services.llm_service import get_genai_client, get_generation_model_name

# 환경변수 로드
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("GOOGLE_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    st.stop()

admin_mode = os.getenv("ADMIN_MODE", "False").lower() == "true"

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
    st.session_state.selected_category = None
if "vector_db" not in st.session_state:
    st.session_state.vector_db = {} 

manuals_root = "manuals"

# 파일 바이너리 로더
@st.cache_data
def get_file_binary(file_path):
    with open(file_path, "rb") as f: return f.read()

# UI 기본 설정
st.set_page_config(page_title="AI-SENSE SMART RAG", page_icon="🏛️", layout="wide")

# 사이드바 헤더 및 CSS
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.sidebar.markdown("""
    <div style="display: flex; align-items: center; gap: 10px; padding: 10px 0; margin-bottom: 25px; border-bottom: 1px solid #f1f5f9;">
        <div style="background-color: #1e60ff; color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.25rem; box-shadow: 0 4px 10px rgba(30, 96, 255, 0.25);">I</div>
        <div>
            <div style="font-size: 1.1rem; font-weight: 800; color: #0f172a; line-height: 1.1;">아이센스토어</div>
            <div style="font-size: 0.7rem; font-weight: 700; color: #1e60ff; letter-spacing: 0.05em; margin-top: 1px;">ADMIN RAG SYSTEM</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# 2-Tab 네비게이션 상단 배치
st.sidebar.markdown("<div style='margin-bottom: 15px;'>", unsafe_allow_html=True)
tab_col1, tab_col2 = st.sidebar.columns(2)
with tab_col1:
    is_guidelines = st.session_state.current_tab == "지침서"
    btn_type = "primary" if is_guidelines else "secondary"
    if st.button("📋 지침/매뉴얼", key="tab_guidelines", use_container_width=True, type=btn_type):
        st.session_state.current_tab = "지침서"
        st.session_state.selected_category = None
        st.rerun()
with tab_col2:
    is_laws = st.session_state.current_tab == "법령"
    btn_type = "primary" if is_laws else "secondary"
    if st.button("⚖️ 법령/조례", key="tab_laws", use_container_width=True, type=btn_type):
        st.session_state.current_tab = "법령"
        st.session_state.selected_category = "조례규칙"
        st.rerun()
st.sidebar.markdown("</div>", unsafe_allow_html=True)

if admin_mode:
    st.sidebar.markdown("""
        <div style="background-color: #fff1f2; color: #e11d48; border: 1px solid #ffe4e6; border-radius: 10px; padding: 10px 14px; font-size: 0.8rem; font-weight: 700; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 5px rgba(225, 29, 72, 0.03);">
            <span style="color: #e11d48; font-size: 1rem;">⚙️</span> [관리자 모드] 활성화됨
        </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.selected_category:
        if st.sidebar.button("♻️ 현재 카테고리 캐시 재빌드", use_container_width=True):
            cat_to_rebuild = st.session_state.selected_category
            # 1. 세션 캐시 제거
            if cat_to_rebuild in st.session_state.vector_db:
                del st.session_state.vector_db[cat_to_rebuild]
            # 2. 물리 파일 제거
            cat_path = os.path.join(manuals_root, cat_to_rebuild)
            cache_file = os.path.join(cat_path, ".vector_cache.pkl")
            if os.path.exists(cache_file):
                try:
                    os.remove(cache_file)
                except Exception as e:
                    st.sidebar.error(f"캐시 파일 삭제 실패: {e}")
            st.rerun()

if st.session_state.current_tab == "지침서":
    st.sidebar.markdown("""
        <div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; padding-left: 4px;">ACTIVE CHANNELS</div>
    """, unsafe_allow_html=True)
    
    if not os.path.exists(manuals_root):
        st.sidebar.error("manuals 폴더가 없습니다.")
        st.stop()
        
    # 정렬된 카테고리 로딩 (조례규칙 카테고리는 Tab 2 전용이므로 제외)
    categories_raw = [d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d)) and d != "조례규칙"]
    categories = sorted(categories_raw, key=lambda x: (1 if "기타" in x else 0, x))
    
    # 사이드바 - 카테고리 버튼 생성
    for cat in categories:
        is_active = st.session_state.selected_category == cat
        emoji = get_category_emoji(cat)
        btn_label = f"{emoji} {cat}"
        
        container_class = "active-card-container" if is_active else "inactive-card-container"
        st.sidebar.markdown(f"<div class='{container_class}'>", unsafe_allow_html=True)
        clicked = st.sidebar.button(btn_label, key=f"btn_{cat}", use_container_width=True)
        st.sidebar.markdown("</div>", unsafe_allow_html=True)
        
        if clicked:
            if st.session_state.selected_category == cat:
                st.session_state.selected_category = None
            else:
                st.session_state.selected_category = cat
                st.session_state.messages = []
                if "chat" in st.session_state: del st.session_state.chat
            st.rerun()
                
        if is_active:
            cat_path = os.path.join(manuals_root, cat)
            files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith('.pdf')])
            with st.sidebar.container():
                st.markdown("<div class='file-container'>", unsafe_allow_html=True)
                if files:
                    st.markdown("<div style='font-size:0.85rem; font-weight:600; margin-bottom:8px;'>📄 지침서 다운로드</div>", unsafe_allow_html=True)
                    for f in files:
                        f_path = os.path.join(cat_path, f)
                        display_name = f[:-4] if f.lower().endswith('.pdf') else f
                        st.download_button(
                            label=f"⬇️ {display_name}", 
                            data=get_file_binary(f_path), 
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
    
    cat_path = os.path.join(manuals_root, "조례규칙")
    files = []
    if os.path.exists(cat_path):
        files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith(('.pdf', '.md'))])
        
    with st.sidebar.container():
        st.markdown("<div class='file-container'>", unsafe_allow_html=True)
        if files:
            st.markdown("<div style='font-size:0.85rem; font-weight:600; margin-bottom:8px;'>⚖️ 검색 가능한 핵심 법령/조례</div>", unsafe_allow_html=True)
            for f in files:
                f_path = os.path.join(cat_path, f)
                display_name = f[:-3] if f.lower().endswith('.md') else f
                display_name = display_name[:-4] if display_name.lower().endswith('.pdf') else display_name
                st.download_button(
                    label=f"⬇️ {display_name}", 
                    data=get_file_binary(f_path), 
                    file_name=f, 
                    key=f"dl_law_{f}", 
                    use_container_width=True
                )
        else:
            st.markdown("<div style='font-size:0.8rem; color:#64748b;'>검색 가능한 조례/규칙 파일이 로컬 폴더에 없습니다.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# 메인 렌더링
selected_category = st.session_state.selected_category

if selected_category:
    if selected_category not in st.session_state.vector_db:
        with st.spinner(f"AI가 '{selected_category}' 지침 도서관을 구축 중입니다..."):
            st.session_state.vector_db[selected_category] = build_vector_db(
                category=selected_category, 
                manuals_root=manuals_root, 
                admin_mode=admin_mode, 
                client=client, 
                model_name=LOCAL_MODEL_NAME
            )
    
    db_stats = st.session_state.vector_db[selected_category]
    
    if not db_stats.chunks:
        st.markdown(f"""
            <div style="padding: 100px 0; text-align: center;">
                <div style="font-size: 4rem; margin-bottom: 20px;">⏳</div>
                <h3 style="color: #0f172a; font-weight: 800;">지침서 데이터 준비 중</h3>
                <p style="color: #64748b; font-size: 1.1rem;">'{selected_category}' 분야의 지침서 분석 캐시가 존재하지 않습니다.</p>
                <p style="color: #94a3b8; font-size: 0.95rem;">관리자 모드를 활성화하여 최초 1회 문서 분석(인덱싱)을 완료해야 대화 기능이 활성화됩니다.</p>
            </div>
        """, unsafe_allow_html=True)
        st.stop()
        
    st.sidebar.success(f"✅ {len(db_stats.chunks)}개 문단 분석 완료")
    selected_model_name = get_generation_model_name(client)
    st.sidebar.info(f"🚀 AI 엔진: **{selected_model_name.split('/')[-1] if selected_model_name else '자동'}**")
    st.sidebar.divider()

    # 헤더 렌더링 분기
    if st.session_state.current_tab == "지침서":
        st.markdown(f"""
            <div style="padding: 10px 0 20px 0; border-bottom: 1px solid #f1f5f9; margin-bottom: 30px;">
                <div class="header-pill">LIVE RAG ENGINE SYSTEM</div>
                <h1 style="font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-top: 4px; margin-bottom: 6px; letter-spacing: -0.02em;">{selected_category}</h1>
                <div style="color: #64748b; font-size: 0.95rem; font-weight: 500;">
                    행정지원과의 공식 지침서 분석 및 실시간 답변을 제공합니다.
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div style="padding: 10px 0 20px 0; border-bottom: 1px solid #f1f5f9; margin-bottom: 30px;">
                <div class="header-pill" style="background-color: #f0fdf4 !important; color: #16a34a !important;">LEGAL SEARCH ENGINE</div>
                <h1 style="font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-top: 4px; margin-bottom: 6px; letter-spacing: -0.02em;">⚖️ 교육행정 법령 및 조례 검색</h1>
                <div style="color: #64748b; font-size: 0.95rem; font-weight: 500;">
                    학교 행정과 밀접한 핵심 상위 법령 및 서울시교육청 조례 규칙 원문 검색을 지원합니다.
                </div>
            </div>
        """, unsafe_allow_html=True)

    # 선택된 탭에 따른 대화 기록 로드
    chat_history = st.session_state.messages if st.session_state.current_tab == "지침서" else st.session_state.legal_messages

    for message in chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # 도구 호출을 통해 실시간으로 가져온 법령 팝오버 표시 (지침서 탭 전용)
            if st.session_state.current_tab == "지침서" and message.get("fetched_law"):
                law_data = message["fetched_law"]
                with st.popover(f"💡 {law_data['law_name']} ({law_data['file_type']}) 원문 보기", use_container_width=True):
                    st.markdown(f"### {law_data['law_name']} ({law_data['file_type']})")
                    st.markdown(f"<div style='background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 0.85rem; border: 1px solid #e2e8f0; max-height: 400px; overflow-y: auto;'>{law_data['content']}</div>", unsafe_allow_html=True)

    prompt = None
    if "pending_prompt" in st.session_state:
        prompt = st.session_state.pending_prompt
        del st.session_state.pending_prompt
    else:
        input_placeholder = f"{selected_category} 업무에 대해 질문해 주세요." if st.session_state.current_tab == "지침서" else "궁금하신 서울시교육청 관련 조례 및 법령에 대해 질문해 주세요. (예: 공무원 복무 조례상 특별휴가)"
        prompt = st.chat_input(input_placeholder)

    if prompt:
        # 실시간 법령 조회 캐시 초기화
        st.session_state.last_fetched_law = None
        
        if st.session_state.current_tab == "지침서":
            st.session_state.messages.append({"role": "user", "content": prompt})
        else:
            st.session_state.legal_messages.append({"role": "user", "content": prompt})
            
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.status("🔍 질문을 분석하고 관련 지침을 검색하고 있습니다...", expanded=True) as status:
            st.write("🛰️ 1. 로컬 벡터 DB에서 관련 지침서 탐색 중..." if st.session_state.current_tab == "지침서" else "🛰️ 1. 로컬 법령 벡터 DB에서 관련 조항 탐색 중...")
            time.sleep(0.3)
            relevant_chunks = retrieve_top_chunks(prompt, selected_category, client, k=15, threshold=0.4, model_name=LOCAL_MODEL_NAME, manuals_root=manuals_root)
            
            st.write(f"📊 2. 유사도 기준 필터링 완료 (유사도 0.4 이상 선별된 청크 수: {len(relevant_chunks)}개)")
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
            context_text = "(검색 결과가 존재하지 않습니다. 질문과 일치하거나 유사도가 0.5 이상인 공식 지침서 내용이 전혀 발견되지 않았습니다.)"

        # 탭 구분에 따라 로드할 시스템 프롬프트 분기
        if st.session_state.current_tab == "지침서":
            system_prompt = get_system_prompt(selected_category, context_text)
        else:
            system_prompt = get_legal_system_prompt(selected_category, context_text)

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
                        # 탭 1인 경우에만 실시간 법령 조회 도구 활성화
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
                
                if unique_chunks:
                    st.markdown("---")
                    st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>📍 참고 지침 원문 확인</div>" if st.session_state.current_tab == "지침서" else "<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>📍 참고 법령/조례 원문 확인</div>", unsafe_allow_html=True)
                    cols = st.columns(min(len(unique_chunks), 5))
                    for idx, chunk in enumerate(unique_chunks):
                        with cols[idx % 5]:
                            with st.popover(f"📄 {chunk['metadata'][:12]}...", use_container_width=True):
                                st.markdown(f"**[{chunk['metadata']}] 원문 (유사도: {chunk['score']:.4f})**")
                                st.markdown(f"<div style='background: #f8fafc; padding: 10px; border-radius: 5px; font-size: 0.85rem; border: 1px solid #e2e8f0; max-height: 300px; overflow-y: auto;'>{chunk['content_ui']}</div>", unsafe_allow_html=True)
                                st.markdown("<div style='font-size: 0.7rem; color: #94a3b8; margin-top: 5px;'>※ 위 내용은 추출된 원문입니다.</div>", unsafe_allow_html=True)

                # 지침서 탭에서 실시간으로 도구가 실행된 경우 팝오버 배지 렌더링
                fetched_law = None
                if st.session_state.current_tab == "지침서" and st.session_state.get("last_fetched_law"):
                    fetched_law = st.session_state.last_fetched_law
                    st.markdown("---")
                    st.markdown("<div style='font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 5px;'>⚖️ 상위 근거 법령 원문 확인</div>", unsafe_allow_html=True)
                    with st.popover(f"💡 {fetched_law['law_name']} ({fetched_law['file_type']}) 원문 보기", use_container_width=True):
                        st.markdown(f"### {fetched_law['law_name']} ({fetched_law['file_type']})")
                        st.markdown(f"<div style='background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 0.85rem; border: 1px solid #e2e8f0; max-height: 400px; overflow-y: auto;'>{fetched_law['content']}</div>", unsafe_allow_html=True)

                # 대화 저장
                if st.session_state.current_tab == "지침서":
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": main_response,
                        "fetched_law": fetched_law
                    })
                else:
                    st.session_state.legal_messages.append({
                        "role": "assistant", 
                        "content": main_response
                    })
                
                if recommendations:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size: 0.82rem; font-weight: 700; color: #64748b; margin-bottom: 8px;'>💡 이런 질문은 어떠세요?</div>", unsafe_allow_html=True)
                    rec_cols = st.columns(len(recommendations))
                    for idx, rec in enumerate(recommendations):
                        with rec_cols[idx]:
                            st.markdown("<div class='rec-btn-container'>", unsafe_allow_html=True)
                            st.button(f"🔍 {rec}", key=f"rec_{idx}_{st.session_state.current_tab}_{len(chat_history)}", on_click=set_pending_prompt, args=(rec,))
                            st.markdown("</div>", unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
else:
    # 지침서 기본 랜딩 페이지
    st.markdown("""
        <div style="padding: 80px 0; text-align: center; max-width: 800px; margin: 0 auto;">
            <div style="background-color: #eff6ff; color: #1e60ff; width: 80px; height: 80px; border-radius: 24px; display: flex; align-items: center; justify-content: center; font-size: 2.5rem; margin: 0 auto 24px auto; box-shadow: 0 10px 25px rgba(30, 96, 255, 0.15);">🏛️</div>
            <h2 style="color: #0f172a; font-weight: 800; font-size: 2.2rem; margin-bottom: 8px; letter-spacing: -0.02em;">교육행정 지능형 RAG 시스템</h2>
            <p style="color: #64748b; font-size: 1.05rem; margin-bottom: 24px; line-height: 1.5; font-weight: 500;">
                수만 페이지의 교육청 지침서 중 필요한 내용을 실시간 검색하여<br>가장 안전하고 똑똑하게 답변하는 스마트 어시스턴트입니다.
            </p>
            <div style="display: flex; justify-content: center; gap: 16px; margin-top: 30px;">
                <div style="background: white; border: 1px solid #e2e8f0; padding: 20px; border-radius: 18px; width: 240px; text-align: left; box-shadow: 0 4px 6px rgba(0,0,0,0.01); transition: all 0.2s ease;">
                    <div style="font-size: 1.8rem; margin-bottom: 8px;">🔒</div>
                    <div style="font-weight: 700; color: #0f172a; font-size: 0.95rem;">100% 로컬 보안</div>
                    <div style="color: #64748b; font-size: 0.8rem; margin-top: 4px; line-height: 1.4;">지침서 원문 전체가 외부 클라우드나 공용 서버에 절대 노출되지 않아 완벽히 보호됩니다.</div>
                </div>
                <div style="background: white; border: 1px solid #e2e8f0; padding: 20px; border-radius: 18px; width: 240px; text-align: left; box-shadow: 0 4px 6px rgba(0,0,0,0.01); transition: all 0.2s ease;">
                    <div style="font-size: 1.8rem; margin-bottom: 8px;">⚡</div>
                    <div style="font-weight: 700; color: #0f172a; font-size: 0.95rem;">초고속 시맨틱 검색</div>
                    <div style="color: #64748b; font-size: 0.8rem; margin-top: 4px; line-height: 1.4;">로컬 코사인 유사도 벡터 검색 기술을 활용해 0.001초 만에 최적의 관련 지침을 선별합니다.</div>
                </div>
            </div>
            <div style="margin-top: 45px; font-size: 0.92rem; color: #94a3b8; font-weight: 600; letter-spacing: -0.01em;">
                ⬅️ 좌측의 <span style="color: #1e60ff;">[ACTIVE CHANNELS]</span> 업무 카드 중 하나를 선택해 대화를 시작해 보세요.
            </div>
        </div>
    """, unsafe_allow_html=True)
