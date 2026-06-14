import time
import os
from google import genai

class FallbackModelsProxy:
    def __init__(self, free_client, paid_client):
        self.free_client = free_client
        self.paid_client = paid_client

    def _call_with_fallback(self, method_name, *args, **kwargs):
        try:
            # 1. 1차 시도: 무료 API 키 활용
            free_method = getattr(self.free_client.models, method_name)
            return free_method(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            # 429 에러 또는 RESOURCE_EXHAUSTED 에러 감지 시
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                try:
                    import streamlit as st
                    # Streamlit 실행 중일 때 우회 안내 표시
                    st.toast("⚠️ 무료 API 할당량이 초과되어 유료 API 키로 자동 전환합니다.", icon="💸")
                except Exception:
                    # CLI 터미널 실행 중일 때 콘솔 출력
                    print("\n[Fallback] ⚠️ 무료 API 할당량이 초과되어 유료 API 키로 자동 전환하여 호출합니다.")
                
                # 2. 2차 시도: 유료 API 키 활용
                paid_method = getattr(self.paid_client.models, method_name)
                return paid_method(*args, **kwargs)
            else:
                # 기타 일반 오류는 그대로 전파
                raise e

    def generate_content(self, *args, **kwargs):
        return self._call_with_fallback("generate_content", *args, **kwargs)

    def generate_content_stream(self, *args, **kwargs):
        return self._call_with_fallback("generate_content_stream", *args, **kwargs)

    def embed_content(self, *args, **kwargs):
        return self._call_with_fallback("embed_content", *args, **kwargs)

    def list(self, *args, **kwargs):
        return self._call_with_fallback("list", *args, **kwargs)


class FallbackGenAIClient:
    def __init__(self, free_api_key, paid_api_key):
        self.free_client = genai.Client(api_key=free_api_key)
        self.paid_client = genai.Client(api_key=paid_api_key)
        self.models = FallbackModelsProxy(self.free_client, self.paid_client)
