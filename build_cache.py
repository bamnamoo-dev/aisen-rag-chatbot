import os
import sys
import hashlib
import pickle
import numpy as np
import faiss
import time
from dotenv import load_dotenv
from google import genai

# Reconfigure stdout/stderr encoding to UTF-8 for Windows console support
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Mock Streamlit to prevent import/runtime errors when importing modules
from unittest.mock import MagicMock
sys.modules['streamlit'] = MagicMock()

# Now we can safely import our classes and functions
from core.parser import RecursiveCharacterTextSplitter, table_to_markdown, parse_single_pdf, parse_single_md
from core.vector_db import LocalVectorDB, get_folder_hash, get_file_hash
from services.llm_service import get_genai_client
import fitz

def get_pdf_chunks_cli(folder_path):
    chunks = []
    if not os.path.exists(folder_path):
        return chunks
    
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.pdf', '.md'))])
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    total_files = len(files)
    print(f"\n[1/2] 📄 문서 파일 파싱을 시작합니다. (총 {total_files}개 파일)")
    
    for f_idx, filename in enumerate(files):
        file_path = os.path.join(folder_path, filename)
        print(f"   -> [{f_idx+1}/{total_files}] 분석 중: {filename}")
        try:
            if filename.lower().endswith('.pdf'):
                file_chunks = parse_single_pdf(file_path, filename, splitter)
                chunks.extend(file_chunks)
            elif filename.lower().endswith('.md'):
                file_chunks = parse_single_md(file_path, filename, splitter)
                chunks.extend(file_chunks)
        except Exception as e:
            print(f"   ❌ {filename} 로드 실패: {e}")
            
    print(f"   ✅ 총 {len(chunks)}개의 의미 청크(문단)로 분할 완료!\n")
    return chunks

def create_embeddings_cli(chunks, client, model_name="gemini-embedding-2"):
    if not chunks:
        return []
    
    texts = [c["content"] for c in chunks]
    embeddings_list = []
    
    batch_size = 100
    total_batches = (len(texts) + batch_size - 1) // batch_size
    print(f"[2/2] 🚀 Google Gemini API를 사용하여 임베딩 분석을 진행합니다. (총 {total_batches}개 배치)")
    
    from google.genai import types
    for i in range(0, len(texts), batch_size):

        batch = texts[i:i + batch_size]
        batch_idx = i // batch_size
        contents_batch = [types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]
        
        max_retries = 10
        retry_delay = 5.0
        success = False
        
        for attempt in range(max_retries):
            try:
                print(f"   -> 임베딩 변환 중 ({batch_idx + 1}/{total_batches} 묶음)...", end="", flush=True)
                response = client.models.embed_content(
                    model=model_name,
                    contents=contents_batch
                )
                for emb in response.embeddings:
                    embeddings_list.append(emb.values)

                success = True
                print(" 완료")
                break
            except Exception as e:
                error_str = str(e)
                if attempt < max_retries - 1:
                    print(f"\n   ⚠️ API 호출 오류 감지 ({error_str})! {retry_delay}초 대기 후 재시도 (시도 {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 1.8
                else:
                    print(f"\n   ❌ 구글 임베딩 API 호출 최종 에러: {e}")
                    return []
        
        if not success:
            print("\n   ❌ 구글 API 트래픽 제한으로 분석이 중단되었습니다.")
            return []
            
        # 유료 티어 속도 향상을 위해 대기시간 단축 (기존 60.0초 -> 0.2초)
        time.sleep(0.2)
            
    return np.array(embeddings_list, dtype=np.float32)

def build_category_cache(category, manuals_root, client, model_name):
    cat_path = os.path.join(manuals_root, category)
    
    # PDF 또는 MD 파일이 아예 없는 폴더는 스캔 대상에서 제외
    files = sorted([f for f in os.listdir(cat_path) if f.lower().endswith(('.pdf', '.md'))])
    if not files:
        return False
        
    current_hash = get_folder_hash(cat_path, model_name)
    
    db = LocalVectorDB(category)
    # 1. 해시가 동일할 시 즉시 완료 처리
    if db.load_local(cat_path, current_hash):
        print(f"   ➔ [{category}] 변경 없음 (캐시가 최신 상태입니다. 건너뜀)")
        return False
        
    print(f"\n📂 [{category}] 변경 감지! 파일 단위 증분 벡터 DB 빌드를 시작합니다. (경로: {cat_path})")
    print(f"🔑 폴더 해시: {current_hash}")
    
    # 캐시 v2.0 초기화 또는 가져오기
    if not hasattr(db, 'file_cache') or not db.file_cache or db.file_cache.get("version") != "2.0":
        db.file_cache = {
            "version": "2.0",
            "hash": "",
            "model_name": model_name,
            "files": {}
        }
        
    # 2.1. 삭제된 파일 캐시 제외
    cached_files = list(db.file_cache["files"].keys())
    for f in cached_files:
        if f not in files:
            del db.file_cache["files"][f]
            print(f"   🗑️ 캐시 제외: {f} (실제 폴더에서 삭제됨)")
            
    # 2.2. 신규/수정 파일 스캔 및 부분 빌드
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    any_change = False
    for filename in files:
        file_path = os.path.join(cat_path, filename)
        try:
            mtime = os.path.getmtime(file_path)
            size = os.path.getsize(file_path)
        except Exception as e:
            print(f"   ❌ {filename} 메타데이터 읽기 실패: {e}")
            continue
            
        f_cache = db.file_cache["files"].get(filename)
        file_hash = get_file_hash(file_path)
        
        is_changed = True
        if f_cache is not None:
            cached_hash = f_cache.get("hash")
            if cached_hash:
                is_changed = (f_cache.get("size") != size or cached_hash != file_hash)
            else:
                is_changed = (f_cache.get("size") != size or f_cache.get("mtime") != mtime)
                if not is_changed:
                    f_cache["hash"] = file_hash
                      
        if is_changed:
            any_change = True
            print(f"   🔄 파일 분석 중: {filename}")
            try:
                if filename.lower().endswith('.pdf'):
                    f_chunks = parse_single_pdf(file_path, filename, splitter)
                elif filename.lower().endswith('.md'):
                    f_chunks = parse_single_md(file_path, filename, splitter)
                else:
                    f_chunks = []
                    
                if f_chunks:
                    # CLI 임베딩 생성 호출
                    f_embeddings = create_embeddings_cli(f_chunks, client, model_name)
                    if len(f_embeddings) == 0:
                        print(f"   ❌ {filename} 임베딩 벡터 생성 실패")
                        sys.exit(1)
                else:
                    f_embeddings = np.array([], dtype=np.float32)
                    
                db.file_cache["files"][filename] = {
                    "mtime": mtime,
                    "size": size,
                    "hash": file_hash,
                    "chunks": f_chunks,
                    "embeddings": f_embeddings
                }
            except Exception as e:
                print(f"   ❌ {filename} 분석 실패: {e}")
                sys.exit(1)
                
    # 2.3. 병합 및 최종 인덱스 재정립
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
        print(f"   🎉 [{category}] 파일 단위 증분 벡터 DB 빌드 완료! (.vector_cache.pkl)")
        return True
    else:
        db.chunks = []
        db.embeddings = None
        db.index = None
        cache_file = os.path.join(cat_path, ".vector_cache.pkl")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception:
                pass
        print(f"   ⚠️ [{category}] 지침서 파일이 없어 캐시가 삭제되었습니다.")
        return False

def main():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 에러: .env 파일에 GOOGLE_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)
        
    manuals_root = "manuals"
    if not os.path.exists(manuals_root):
        print(f"❌ 에러: {manuals_root} 폴더가 존재하지 않습니다.")
        sys.exit(1)
        
    model_name = "gemini-embedding-2"
    client = get_genai_client(api_key)
    
    # 카테고리가 인자로 전달된 경우
    if len(sys.argv) >= 2:
        category = sys.argv[1]
        build_category_cache(category, manuals_root, client, model_name)
    else:
        # 인자가 없는 경우: 모든 카테고리 자동 스캔 및 변경된 폴더만 빌드
        print("🔍 모든 지침서 폴더의 변경 사항(파일 추가/수정/삭제)을 감지합니다...")
        categories = sorted([d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d))])
        
        rebuilt_count = 0
        for cat in categories:
            if build_category_cache(cat, manuals_root, client, model_name):
                rebuilt_count += 1
                
        if rebuilt_count == 0:
            print("\n✅ 모든 카테고리가 최신 상태입니다. 업데이트할 변경 사항이 없습니다.")
        else:
            print(f"\n🎉 총 {rebuilt_count}개의 카테고리 벡터 DB가 성공적으로 갱신되었습니다!")

if __name__ == "__main__":
    main()
