import streamlit as st
from google import genai
from app_config import GEMINI_PRIORITY

# 제미나이 클라이언트 초기화 (캐싱 적용)
@st.cache_resource
def get_genai_client(api_key):
    return genai.Client(api_key=api_key)

@st.cache_resource
def get_generation_model_name(_client, exclude_models=None):
    """사용 가능한 채팅 모델 명칭 자동 확인 (안정적인 1.5 우선)"""
    try:
        if exclude_models is None: exclude_models = []
        models = _client.models.list()
        available = [m.name for m in models if "generateContent" in m.supported_actions]
        
        # 1. 접두사 포함해서 찾기
        for p in GEMINI_PRIORITY:
            full_p = f"models/{p}"
            if full_p in available and full_p not in exclude_models:
                return full_p
        
        # 2. 접두사 없이 찾기
        for p in GEMINI_PRIORITY:
            if p in available and p not in exclude_models:
                return p
        
        # 3. 하드코딩 백업 (리스트에 없어도 시도)
        for p in GEMINI_PRIORITY:
            full_p = f"models/{p}"
            if full_p not in exclude_models:
                return full_p
                
        return None
    except:
        return "models/gemini-1.5-flash"
