import os
import hashlib
import pickle
import numpy as np
import faiss
import logging
import streamlit as st
import time
from core.parser import get_pdf_chunks

class LocalVectorDB:
    def __init__(self, category):
        self.category = category
        self.chunks = []
        self.embeddings = None
        self.index = None

    def build_index(self):
        """FAISS 인덱스 빌드 및 코사인 유사도 연산 준비"""
        if self.embeddings is not None and len(self.embeddings) > 0:
            # L2 정규화 (코사인 유사도를 Inner Product로 풀기 위함)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            normalized = self.embeddings / (norms + 1e-10)
            
            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(normalized.astype('float32'))
        else:
            self.index = None

    def save_local(self, folder_path, current_hash):
        """인덱싱된 청크와 임베딩 데이터를 로컬 파일로 최적화하여 저장"""
        cache_file = os.path.join(folder_path, ".vector_cache.pkl")
        data = {
            "hash": current_hash,
            "chunks": self.chunks,
            "embeddings": self.embeddings
        }
        with open(cache_file, "wb") as f:
            pickle.dump(data, f)

    def load_local(self, folder_path, current_hash):
        """로컬 파일에서 인덱싱된 데이터를 로드하고 FAISS 인덱스 재빌드"""
        cache_file = os.path.join(folder_path, ".vector_cache.pkl")
        if not os.path.exists(cache_file):
            return False
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            if data.get("hash") == current_hash and data.get("chunks"):
                self.chunks = data["chunks"]
                self.embeddings = data["embeddings"]
                # FAISS 인덱스 빌드 실패해도 chunks는 유지 (키워드 검색 폴백으로 동작)
                try:
                    self.build_index()
                except Exception as idx_e:
                    st.sidebar.warning(f"⚠️ FAISS 인덱스 빌드 실패 (키워드 검색 폴백 활성화): {idx_e}")
                    self.index = None
                return True
            elif not data.get("chunks"):
                st.sidebar.warning("⚠️ 캐시 파일에 청크 데이터가 없습니다. 재빌드가 필요합니다.")
            else:
                st.sidebar.warning(f"⚠️ 캐시 해시 불일치 (파일 변경 감지). 재빌드가 필요합니다.")
        except Exception as e:
            st.sidebar.warning(f"캐시 로드 실패: {e}")
        return False

def create_embeddings(chunks, client, model_name="gemini-embedding-2"):
    """Google Gemini API의 Batch Embedding 기술을 사용하여 문단들을 숫자로 초고속 분석 (429 자동 우회 포함)"""
    if not chunks:
        return []
    
    texts = [c["content"] for c in chunks]
    embeddings_list = []
    
    # API 배치 크기 한도(최대 100개)에 맞춤
    batch_size = 100
    total_batches = (len(texts) + batch_size - 1) // batch_size
    
    progress_bar = st.sidebar.progress(0.0)
    status_text = st.sidebar.empty()
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_idx = i // batch_size
        from google.genai import types
        contents_batch = [types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]


        
        # 429 Too Many Requests 대비 지능형 재시도 루프 (Exponential Backoff)
        max_retries = 10
        retry_delay = 5.0  # 초기 대기시간 5초
        success = False
        
        for attempt in range(max_retries):
            try:
                status_text.text(f"🚀 분석 진행 중 ({batch_idx + 1}/{total_batches} 묶음)...")
                response = client.models.embed_content(
                    model=model_name,
                    contents=contents_batch
                )
                for emb in response.embeddings:
                    embeddings_list.append(emb.values)
                success = True
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    st.sidebar.warning(f"⚠️ 구글 API 트래픽 한도 도달! {retry_delay}초 동안 대기 후 다시 시도합니다. (시도 {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 1.8  # 대기시간 점진적 증가
                else:
                    st.error(f"구글 임베딩 API 호출 에러: {e}")
                    return []
        
        if not success:
            st.error("구글 API 트래픽 제한이 일시적으로 중단되었습니다. 잠시 후 다시 시도해 주세요.")
            return []
            
        # 유료 티어 속도 향상을 위해 대기시간 단축 (기존 60.0초 -> 0.2초)
        time.sleep(0.2)
        progress_bar.progress(float(batch_idx + 1) / total_batches)
        
    progress_bar.empty()
    status_text.empty()
    return np.array(embeddings_list, dtype=np.float32)

def get_folder_hash(folder_path, model_name):
    """폴더 구성 및 사용 모델 정보를 조합하여 해시 생성 (줄바꿈 정규화 포함)"""
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.pdf', '.md'))])
    hasher = hashlib.md5()
    hasher.update(model_name.encode())
    for f in files:
        f_path = os.path.join(folder_path, f)
        hasher.update(f.encode())
        if f.lower().endswith('.md'):
            # 마크다운 파일은 OS별 줄바꿈(\\r\\n vs \\n) 차이로 인한 사이즈 불일치 방지를 위해 정규화 후 해시 계산
            try:
                with open(f_path, "r", encoding="utf-8") as file:
                    content = file.read().replace('\r\n', '\n')
                hasher.update(str(len(content.encode('utf-8'))).encode())
            except Exception:
                hasher.update(str(os.path.getsize(f_path)).encode())
        else:
            hasher.update(str(os.path.getsize(f_path)).encode())
    return hasher.hexdigest()

@st.cache_resource
def build_vector_db(category, manuals_root, admin_mode, _client, model_name="gemini-embedding-2", rebuild_trigger=0):
    """지침서 폴더의 PDF들을 분석하여 로컬 벡터 DB 구축 및 FAISS 인덱싱"""
    cat_path = os.path.join(manuals_root, category)
    current_hash = get_folder_hash(cat_path, model_name)
    
    db = LocalVectorDB(category)
    
    # 1. 기존 캐시 파일 확인 및 로드
    if db.load_local(cat_path, current_hash):
        return db
            
    # 2. 캐시가 없거나 파일이 변경된 경우
    if not admin_mode:
        logger = logging.getLogger("sen-chatbot")
        logger.warning(f"⚠️ [ADMIN ALERT] '{category}' 카테고리의 벡터 캐시 파일이 없거나 유효하지 않습니다. 분석(인덱싱)이 필요합니다.")
        
        st.info(f"ℹ️ 현재 '{category}' 분야 지침 도서관의 데이터베이스가 준비 중입니다. 잠시만 기다려 주시거나 관리자에게 문의하세요.")
        st.sidebar.warning("⚠️ 지침서 분석 캐시가 유효하지 않습니다. 관리자 모드를 활성화하여 분석을 진행하십시오.")
        return db

    # 관리자 모드일 경우에만 새로 분석 시작
    st.sidebar.info("⚙️ [관리자] 새 PDF 문서 의미 분할 및 구글 임베딩 분석을 진행합니다...")
    chunks = get_pdf_chunks(cat_path)
    embeddings = create_embeddings(chunks, _client, model_name)
    
    if embeddings is not None and len(embeddings) > 0:
        db.chunks = chunks
        db.embeddings = embeddings
        db.build_index()
        db.save_local(cat_path, current_hash)
        st.sidebar.success("🎉 분석 결과 로컬 파일로 저장 완료!")
        
    return db

def get_priority_files(category, manuals_root="manuals"):
    """우선순위 지침서/법령 파일 목록 조회 (키워드 매칭 및 가장 최근 수정된 파일)"""
    cat_path = os.path.join(manuals_root, category)
    if not os.path.exists(cat_path):
        return set()
        
    priority_files = set()
    try:
        files = [f for f in os.listdir(cat_path) if f.lower().endswith(('.pdf', '.md'))]
    except Exception:
        return set()
        
    latest_file = None
    latest_mtime = -1
    
    for f in files:
        f_path = os.path.join(cat_path, f)
        f_lower = f.lower()
        
        # 1. 파일명 키워드 검사 (2026, 최신, _new)
        if "(2026)" in f_lower or "2026" in f_lower or "(최신)" in f_lower or "최신" in f_lower or "_new" in f_lower:
            priority_files.add(f)
            
        # 2. 파일 수정 시간(mtime) 검사
        try:
            mtime = os.path.getmtime(f_path)
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = f
        except Exception:
            pass
            
    if latest_file:
        priority_files.add(latest_file)
        
    return priority_files

def retrieve_top_chunks(query, db, client, k=15, threshold=0.4, model_name="gemini-embedding-2", manuals_root="manuals"):
    """질문과 관련 있는 지침 조각을 FAISS로 검색하고 유사도 임계치 필터링, 최신 파일 가중치(Boosting) 부여, 맥락 보강 및 Reranking"""
    if db is None:
        return []
    
    chunks = db.chunks
    index = db.index

    # 1. 우선순위 파일 식별
    priority_files = get_priority_files(db.category, manuals_root)
    search_k = max(50, k * 2)

    if index is None or db.embeddings is None or not len(db.embeddings):
        # 키워드 기반 검색 백업
        query_words = query.split()
        scores = [sum(1 for word in query_words if word in c["content"]) for c in chunks]
        top_indices = np.argsort(scores)[-search_k:][::-1]
        valid_indices = [idx for idx in top_indices if scores[idx] > 0]
        scores_filtered = [float(scores[idx]) for idx in valid_indices]
    else:
        # Google API를 이용한 단일 쿼리 고속 임베딩
        try:
            query_response = client.models.embed_content(
                model=model_name,
                contents=query
            )
            query_values = query_response.embeddings[0].values
            query_vec = np.array([query_values])
            
            query_norm = np.linalg.norm(query_vec, axis=1, keepdims=True)
            normalized_query = query_vec / (query_norm + 1e-10)
            
            scores, indices = index.search(normalized_query.astype('float32'), search_k)
            
            scores = scores[0]
            indices = indices[0]
            
            valid_indices = []
            scores_filtered = []
            for idx, score in zip(indices, scores):
                if idx != -1 and score >= threshold:
                    valid_indices.append(int(idx))
                    scores_filtered.append(float(score))
        except Exception as e:
            # API 에러 시 키워드 백업 작동
            st.warning(f"임베딩 검색 에러로 인해 키워드 백업 검색을 구동합니다: {e}")
            query_words = query.split()
            scores = [sum(1 for word in query_words if word in c["content"]) for c in chunks]
            top_indices = np.argsort(scores)[-search_k:][::-1]
            valid_indices = [idx for idx in top_indices if scores[idx] > 0]
            scores_filtered = [0.4 for idx in valid_indices] # 백업 기본 유사도 부여
    
    results = []
    for idx, score in zip(valid_indices, scores_filtered):
        start_idx = max(0, idx - 1)
        end_idx = min(len(chunks), idx + 2)
        
        context_text = ""
        for i in range(start_idx, end_idx):
            prefix = "▶ " if i == idx else "  "
            context_text += f"{prefix}{chunks[i]['content']}\n"
            
        metadata = chunks[idx]["metadata"]
        
        # 최신 지침 가중치 룰 (Score Boosting) 적용
        is_priority = False
        for p_file in priority_files:
            if metadata.startswith(p_file):
                is_priority = True
                break
                
        final_score = score
        if is_priority:
            final_score += 0.1  # 보너스 점수 +0.1 부여
            
        results.append({
            "content_llm": chunks[idx]["content"].strip(),
            "content_ui": context_text.strip(),
            "metadata": metadata,
            "score": final_score,
            "original_score": score,
            "is_priority": is_priority
        })
        
    # 부스팅 스코어 기준으로 재정렬 (Reranking)
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results[:k]
