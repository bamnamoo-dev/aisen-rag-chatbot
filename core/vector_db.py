import os
import hashlib
import pickle
import numpy as np
import faiss
import logging
import streamlit as st
import time
import re
from core.parser import get_pdf_chunks

def simple_korean_tokenizer(text):
    """한국어 행정 용어 및 조항 번호 검색 최적화를 위한 경량 정규식 기반 토크나이저"""
    if not text:
        return []
    text = text.lower()
    # 특수 문자 제거 (법령 표기용 언더바, 대시, 수치 보존)
    cleaned = re.sub(r'[^a-zA-Z0-9가-힣ㄱ-ㅎㅏ-ㅣ_수-]', ' ', text)
    words = cleaned.split()
    
    tokens = []
    for w in words:
        if len(w) >= 2:
            tokens.append(w)
            # 어근 추출 (기본 조사 은,는,이,가,을,를,의,에,로,으로,에서,에게,와,과,하고,이다 등 제거)
            stem = re.sub(r'(은|는|이|가|을|를|의|에|로|으로|에서|에게|와|과|하고|이다|입니다|하나요|인가요)$', '', w)
            if len(stem) >= 2 and stem != w:
                tokens.append(stem)
            # 조항 번호 추출 (예: 제30조 -> 30조, 30)
            if '조' in w:
                nums = re.findall(r'\d+', w)
                for num in nums:
                    tokens.append(f"{num}조")
                    tokens.append(num)
        elif len(w) == 1 and (w.isdigit() or w.isalpha()):
            tokens.append(w)
    return tokens

class LocalVectorDB:
    def __init__(self, category):
        self.category = category
        self.chunks = []
        self.embeddings = None
        self.index = None
        self.bm25 = None

    def build_index(self):
        """FAISS 인덱스 빌드 및 코사인 유사도 연산 준비, 로컬 BM25 빌드 포함"""
        if self.embeddings is not None and len(self.embeddings) > 0:
            # L2 정규화 (코사인 유사도를 Inner Product로 풀기 위함)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            normalized = self.embeddings / (norms + 1e-10)
            
            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(normalized.astype('float32'))
        else:
            self.index = None
            
        # BM25 인덱스 빌드
        self.build_bm25_index()

    def build_bm25_index(self):
        """로컬 메모리상에 BM25 인덱스 실시간 생성 (API 호출 없음)"""
        if self.chunks:
            try:
                from rank_bm25 import BM25Okapi
                tokenized_corpus = [simple_korean_tokenizer(c["content"]) for c in self.chunks]
                self.bm25 = BM25Okapi(tokenized_corpus)
            except Exception as e:
                try:
                    st.sidebar.warning(f"⚠️ BM25 인덱스 빌드 실패: {e}")
                except Exception:
                    print(f"⚠️ BM25 인덱스 빌드 실패: {e}")
                self.bm25 = None
        else:
            self.bm25 = None

    def save_local(self, folder_path, current_hash):
        """인덱싱된 청크와 임베딩 데이터를 로컬 파일로 최적화하여 저장"""
        cache_file = os.path.join(folder_path, ".vector_cache.pkl")
        
        # self.file_cache 구조가 없거나 비어있는 경우 새로 초기화하여 저장
        if not hasattr(self, 'file_cache') or not self.file_cache:
            self.file_cache = {
                "version": "2.0",
                "hash": current_hash,
                "model_name": "gemini-embedding-2",
                "files": {}
            }
        
        # 최종 병합된 chunks와 embeddings를 탑레벨에도 캐시하여 고속 로딩 지원
        self.file_cache["hash"] = current_hash
        self.file_cache["chunks"] = self.chunks
        self.file_cache["embeddings"] = self.embeddings
        
        with open(cache_file, "wb") as f:
            pickle.dump(self.file_cache, f)

    def load_local(self, folder_path, current_hash):
        """로컬 파일에서 인덱싱된 데이터를 로드하고 FAISS 인덱스 재빌드"""
        cache_file = os.path.join(folder_path, ".vector_cache.pkl")
        if not os.path.exists(cache_file):
            return False
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            
            # v1.0 구버전 캐시 마이그레이션 대응
            # v1.0 데이터의 경우 "version" 키가 없음
            is_v2 = data.get("version") == "2.0"
            
            if not is_v2:
                # v1.0 캐시를 v2.0 포맷으로 즉시 자동 마이그레이션 (임베딩 API 호출 재연산 방지)
                try:
                    files_dict = {}
                    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.pdf', '.md'))])
                    
                    for f_name in files:
                        f_path = os.path.join(folder_path, f_name)
                        try:
                            mtime = os.path.getmtime(f_path)
                            size = os.path.getsize(f_path)
                        except Exception:
                            mtime = 0.0
                            size = 0
                            
                        f_chunks = []
                        f_embs_list = []
                        for idx, chunk in enumerate(data.get("chunks", [])):
                            chunk_filename = get_filename_from_metadata(chunk["metadata"])
                            if chunk_filename == f_name:
                                f_chunks.append(chunk)
                                if data.get("embeddings") is not None and idx < len(data["embeddings"]):
                                    f_embs_list.append(data["embeddings"][idx])
                                    
                        files_dict[f_name] = {
                            "mtime": mtime,
                            "size": size,
                            "chunks": f_chunks,
                            "embeddings": np.array(f_embs_list, dtype=np.float32) if f_embs_list else np.array([], dtype=np.float32)
                        }
                        
                    migrated_data = {
                        "version": "2.0",
                        "hash": data.get("hash"),
                        "model_name": data.get("model_name", "gemini-embedding-2"),
                        "files": files_dict,
                        "chunks": data.get("chunks", []),
                        "embeddings": data.get("embeddings")
                    }
                    data = migrated_data
                    is_v2 = True
                    
                    # 마이그레이션된 v2 포맷을 즉시 디스크에 영구 저장
                    with open(cache_file, "wb") as f_out:
                        pickle.dump(data, f_out)
                except Exception as migration_e:
                    st.sidebar.warning(f"⚠️ 구버전 캐시 자동 마이그레이션 실패: {migration_e}")
            
            # 1. 완벽한 해시 일치 시 즉시 로딩 (변경 없음)
            if data.get("hash") == current_hash and data.get("chunks") is not None:
                self.chunks = data["chunks"]
                self.embeddings = data["embeddings"]
                self.file_cache = data
                try:
                    self.build_index()
                except Exception as idx_e:
                    st.sidebar.warning(f"⚠️ FAISS 인덱스 빌드 실패: {idx_e}")
                    self.index = None
                return True
                
            # 2. 해시 불일치 시: v2인 경우, 캐시 데이터 자체는 일단 멤버 필드(self.file_cache)에 살려두고 로딩 프로세스 내부에서 증분 비교를 함
            if is_v2:
                self.file_cache = data
                return False
                
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
    
    # 1. 기존 캐시 파일 확인 및 로드 (해시 일치 시 즉시 리턴)
    if db.load_local(cat_path, current_hash):
        # 구버전 캐시(v1.0)이거나 임시 마이그레이션 캐시인 경우, admin_mode가 활성화되어 있을 때만 증분 빌드를 위해 계속 진행함.
        # 일반 사용자 모드(admin_mode=False)에서는 기존 로드된 데이터를 그대로 즉시 사용하도록 리턴함.
        if not admin_mode:
            return db
        if hasattr(db, 'file_cache') and db.file_cache.get("version") == "2.0":
            if "migrated_v1_backup.pdf" not in db.file_cache.get("files", {}):
                return db
            
    # 2. 캐시가 없거나 파일이 변경된 경우 (해시 불일치)
    if not admin_mode:
        # 비어있는 인덱스라도 키워드 검색 Fallback을 위해 캐시에 남아있는 chunks/embeddings 정보를 긁어모아 탑레벨에 탑재
        if hasattr(db, 'file_cache') and "files" in db.file_cache:
            merged_chunks = []
            merged_embs = []
            for f_info in db.file_cache["files"].values():
                merged_chunks.extend(f_info["chunks"])
                if len(f_info["embeddings"]) > 0:
                    merged_embs.append(f_info["embeddings"])
            db.chunks = merged_chunks
            if merged_embs:
                db.embeddings = np.vstack(merged_embs)
                try:
                    db.build_index()
                except Exception:
                    pass
        
        logger = logging.getLogger("sen-chatbot")
        logger.warning(f"⚠️ [ADMIN ALERT] '{category}' 카테고리의 벡터 캐시 파일이 없거나 유효하지 않습니다. 분석(인덱싱)이 필요합니다.")
        
        st.info(f"ℹ️ 현재 '{category}' 분야 지침 도서관의 데이터베이스가 준비 중입니다. 잠시만 기다려 주시거나 관리자에게 문의하세요.")
        st.sidebar.warning("⚠️ 지침서 분석 캐시가 유효하지 않습니다. 관리자 모드를 활성화하여 분석을 진행하십시오.")
        return db

    # 관리자 모드일 경우에만 증분 인덱싱 빌드 시작
    st.sidebar.info("⚙️ [관리자] 새 PDF 문서 의미 분할 및 구글 임베딩 분석을 진행합니다...")
    
    # 캐시 v2.0 초기화 또는 획득
    if not hasattr(db, 'file_cache') or not db.file_cache or db.file_cache.get("version") != "2.0":
        db.file_cache = {
            "version": "2.0",
            "hash": "",
            "model_name": model_name,
            "files": {}
        }
        
    # 현재 디렉토리 내 실제 파일 목록
    files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith(('.pdf', '.md'))])
    
    # 2.1. 삭제된 파일 캐시 제외
    cached_files = list(db.file_cache["files"].keys())
    for f in cached_files:
        if f not in files:
            del db.file_cache["files"][f]
            st.sidebar.info(f"🗑️ 캐시 제외: {f} (실제 폴더에서 삭제됨)")
            
    # 2.2. 신규/수정 파일 분석 및 임베딩 생성
    from core.parser import RecursiveCharacterTextSplitter, parse_single_pdf, parse_single_md
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    any_change = False
    for filename in files:
        file_path = os.path.join(cat_path, filename)
        try:
            mtime = os.path.getmtime(file_path)
            size = os.path.getsize(file_path)
        except Exception as e:
            st.sidebar.error(f"❌ {filename} 메타데이터 읽기 실패: {e}")
            continue
            
        f_cache = db.file_cache["files"].get(filename)
        # 변경 여부 확인 (캐시가 없거나, mtime이 다르거나, 크기가 다른 경우)
        is_changed = (f_cache is None or 
                      f_cache.get("mtime") != mtime or 
                      f_cache.get("size") != size)
                      
        if is_changed:
            any_change = True
            st.sidebar.info(f"🔄 파싱 및 분석 중: {filename}")
            try:
                if filename.lower().endswith('.pdf'):
                    f_chunks = parse_single_pdf(file_path, filename, splitter)
                elif filename.lower().endswith('.md'):
                    f_chunks = parse_single_md(file_path, filename, splitter)
                else:
                    f_chunks = []
                    
                if f_chunks:
                    f_embeddings = create_embeddings(f_chunks, _client, model_name)
                else:
                    f_embeddings = np.array([], dtype=np.float32)
                    
                db.file_cache["files"][filename] = {
                    "mtime": mtime,
                    "size": size,
                    "chunks": f_chunks,
                    "embeddings": f_embeddings
                }
            except Exception as e:
                st.sidebar.error(f"❌ {filename} 분석 실패: {e}")
                
    # 2.3. 최종 병합 및 정렬 적용
    merged_chunks = []
    merged_embs = []
    for filename in files:
        f_info = db.file_cache["files"].get(filename)
        if f_info and f_info["chunks"]:
            merged_chunks.extend(f_info["chunks"])
            if len(f_info["embeddings"]) > 0:
                merged_embs.append(f_info["embeddings"])
                
    if merged_chunks:
        db.chunks = merged_chunks
        if merged_embs:
            db.embeddings = np.vstack(merged_embs)
        else:
            db.embeddings = np.array([], dtype=np.float32)
            
        db.build_index()
        db.save_local(cat_path, current_hash)
        st.sidebar.success("🎉 파일 단위 증분 분석 완료 및 캐시 저장!")
    else:
        db.chunks = []
        db.embeddings = None
        db.index = None
        # 파일이 없을 시 기존 캐시 파일 완전 삭제
        cache_file = os.path.join(cat_path, ".vector_cache.pkl")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception:
                pass
                
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

def get_filename_from_metadata(metadata):
    """청크 메타데이터로부터 순수 파일명을 파싱하여 정규화 및 정밀 매칭을 돕는 헬퍼 함수"""
    if not metadata:
        return ""
    cleaned = metadata.strip()
    # 대괄호로 둘러싸인 형태 ([파일명 - ...p]) 대응
    if cleaned.startswith('['):
        cleaned = cleaned[1:]
    if cleaned.endswith(']'):
        cleaned = cleaned[:-1]
    
    # " - "로 구분된 첫 번째 항목(파일명) 분리
    parts = cleaned.split(" - ")
    if parts:
        return parts[0].strip()
    return cleaned

def retrieve_top_chunks(query, db, client, k=15, threshold=0.4, model_name="gemini-embedding-2", manuals_root="manuals"):
    """질문과 관련 있는 지침 조각을 FAISS와 로컬 BM25를 결합해 하이브리드로 검색하고 유사도 임계치 필터링, 최신 파일 가중치(Boosting) 부여, 맥락 보강 및 Reranking"""
    if db is None or not db.chunks:
        return []
    
    chunks = db.chunks
    index = db.index
    bm25 = db.bm25

    # 1. 우선순위 파일 식별
    priority_files = get_priority_files(db.category, manuals_root)
    # 하이브리드 대조군 확장을 위해 넉넉한 1차 탐색 범위(100개) 지정
    search_k = max(100, k * 3)

    # 2. 로컬 BM25 스코어 계산
    query_tokens = simple_korean_tokenizer(query)
    bm25_scores = []
    max_bm25 = 0.0
    if bm25 is not None and query_tokens:
        try:
            bm25_scores = bm25.get_scores(query_tokens)
            max_bm25 = float(max(bm25_scores)) if len(bm25_scores) > 0 else 0.0
        except Exception:
            bm25_scores = []

    # 3. 임베딩(FAISS) 또는 키워드 단독 백업 분기
    if index is None or db.embeddings is None or not len(db.embeddings):
        # API 장애 또는 임베딩 미구축 시: 순수 로컬 BM25 점수로 스케일링 처리
        if len(bm25_scores) > 0 and max_bm25 > 0.0:
            top_indices = np.argsort(bm25_scores)[-search_k:][::-1]
            valid_indices = [idx for idx in top_indices if bm25_scores[idx] > 0]
            scores_filtered = [0.4 + (float(bm25_scores[idx]) / max_bm25) * 0.4 for idx in valid_indices]
        else:
            # BM25도 실패 시: 단순 단어 띄어쓰기 빈도 매칭 백업
            query_words = query.split()
            simple_scores = [sum(1 for word in query_words if word in c["content"]) for c in chunks]
            top_indices = np.argsort(simple_scores)[-search_k:][::-1]
            valid_indices = [idx for idx in top_indices if simple_scores[idx] > 0]
            total_words = len(query_words)
            scores_filtered = [0.4 + (float(simple_scores[idx]) / total_words) * 0.4 if total_words > 0 else 0.4 for idx in valid_indices]
    else:
        # 정상 상태: FAISS (시맨틱) + BM25 (어휘) 하이브리드 검색 결합
        try:
            # Google API를 이용한 단일 쿼리 고속 임베딩
            query_response = client.models.embed_content(
                model=model_name,
                contents=query
            )
            query_values = query_response.embeddings[0].values
            query_vec = np.array([query_values])
            
            query_norm = np.linalg.norm(query_vec, axis=1, keepdims=True)
            normalized_query = query_vec / (query_norm + 1e-10)
            
            # FAISS 의미 검색 후보군 탐색
            faiss_scores, faiss_indices = index.search(normalized_query.astype('float32'), search_k)
            faiss_scores = faiss_scores[0]
            faiss_indices = faiss_indices[0]
            
            # FAISS 인덱스 맵 구성 (인덱스 -> 코사인 스코어)
            faiss_map = {}
            for idx, score in zip(faiss_indices, faiss_scores):
                if idx != -1:
                    faiss_map[int(idx)] = float(score)
                    
            # BM25 후보군 탐색
            bm25_indices = []
            if len(bm25_scores) > 0 and max_bm25 > 0.0:
                # BM25 상위 점수 인덱스 추출
                bm25_indices = np.argsort(bm25_scores)[-search_k:][::-1]
                # 실질 매칭 단어가 있는 인덱스만 필터
                bm25_indices = [int(idx) for idx in bm25_indices if bm25_scores[idx] > 0]
                
            # 후보군 합집합 구성
            union_indices = list(set(list(faiss_map.keys()) + bm25_indices))
            
            # 각 후보군 인덱스에 대해 하이브리드 스코어 계산 및 정규화
            valid_indices = []
            scores_filtered = []
            for idx in union_indices:
                # 1) FAISS 코사인 유사도
                if idx in faiss_map:
                    cos_score = faiss_map[idx]
                else:
                    # FAISS 상위권에는 없지만 BM25에는 걸린 경우, 직접 코사인 유사도 연산
                    emb_idx = db.embeddings[idx]
                    emb_idx_norm = emb_idx / (np.linalg.norm(emb_idx) + 1e-10)
                    cos_score = float(np.dot(emb_idx_norm, normalized_query[0]))
                
                # 2) BM25 스코어
                if len(bm25_scores) > 0 and max_bm25 > 0.0:
                    bm25_score = float(bm25_scores[idx]) / max_bm25
                else:
                    bm25_score = 0.0
                
                # 3) 가중합 결합 (FAISS 0.6 : BM25 0.4)
                hybrid_score = 0.6 * cos_score + 0.4 * bm25_score
                
                # 유사도 임계치 threshold 필터링
                if hybrid_score >= threshold:
                    valid_indices.append(idx)
                    scores_filtered.append(hybrid_score)
            
            # 스코어 높은 순으로 정렬
            if valid_indices:
                sort_order = np.argsort(scores_filtered)[::-1]
                valid_indices = [valid_indices[i] for i in sort_order]
                scores_filtered = [scores_filtered[i] for i in sort_order]
                
        except Exception as api_e:
            st.sidebar.warning(f"⚠️ 하이브리드 검색 오류로 키워드 매칭 폴백: {api_e}")
            if len(bm25_scores) > 0 and max_bm25 > 0.0:
                top_indices = np.argsort(bm25_scores)[-search_k:][::-1]
                valid_indices = [idx for idx in top_indices if bm25_scores[idx] > 0]
                scores_filtered = [0.4 + (float(bm25_scores[idx]) / max_bm25) * 0.4 for idx in valid_indices]
            else:
                query_words = query.split()
                simple_scores = [sum(1 for word in query_words if word in c["content"]) for c in chunks]
                top_indices = np.argsort(simple_scores)[-search_k:][::-1]
                valid_indices = [idx for idx in top_indices if simple_scores[idx] > 0]
                total_words = len(query_words)
                scores_filtered = [0.4 + (float(simple_scores[idx]) / total_words) * 0.4 if total_words > 0 else 0.4 for idx in valid_indices]
    
    results = []
    for idx, score in zip(valid_indices, scores_filtered):
        start_idx = max(0, idx - 1)
        end_idx = min(len(chunks), idx + 2)
        
        current_metadata = chunks[idx]["metadata"]
        current_filename = get_filename_from_metadata(current_metadata)
        
        context_text = ""
        for i in range(start_idx, end_idx):
            prefix = "▶ " if i == idx else "  "
            i_metadata = chunks[i]["metadata"]
            i_filename = get_filename_from_metadata(i_metadata)
            
            # 파일 경계선에서의 맥락 오염(Context Pollution) 방지: 같은 파일의 청크일 때만 앞뒤 맥락 보강에 포함
            if i == idx or i_filename == current_filename:
                context_text += f"{prefix}{chunks[i]['content']}\n"
                
        # 최신 지침 가중치 룰 (Score Boosting) 적용
        is_priority = False
        for p_file in priority_files:
            # metadata.startswith(p_file) 대신 p_file in metadata 및 정밀 파일명 일치를 사용해 버그 해결
            if p_file in current_metadata or p_file in current_filename:
                is_priority = True
                break
                
        final_score = score
        if is_priority:
            final_score += 0.1  # 보너스 점수 +0.1 부여
            
        results.append({
            "content_llm": chunks[idx]["content"].strip(),
            "content_ui": context_text.strip(),
            "metadata": current_metadata,
            "score": final_score,
            "original_score": score,
            "is_priority": is_priority
        })
        
    # 부스팅 스코어 기준으로 재정렬 (Reranking)
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results[:k]
