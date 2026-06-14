import streamlit as st
import os
from google import genai
from app_config import GEMINI_PRIORITY
from services.fallback_client import FallbackGenAIClient

# 제미나이 클라이언트 초기화 (캐싱 적용)
@st.cache_resource
def get_genai_client(api_key):
    # 환경변수에서 이중 API 키를 가져옵니다. (없을 시 기본 api_key를 무료 키로 간주)
    free_key = os.getenv("GEMINI_FREE_API_KEY") or api_key
    paid_key = os.getenv("GEMINI_PAID_API_KEY")
    
    if free_key and paid_key:
        return FallbackGenAIClient(free_key, paid_key)
    else:
        # 이중 키 미설정 시 기존 싱글 키 연동 유지 (하위 호환성 보장)
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
