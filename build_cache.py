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
from core.parser import RecursiveCharacterTextSplitter, table_to_markdown
from core.vector_db import LocalVectorDB, get_folder_hash
import fitz

def get_pdf_chunks_cli(folder_path):
    chunks = []
    if not os.path.exists(folder_path):
        return chunks
    
    pdf_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')])
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    total_files = len(pdf_files)
    print(f"\n[1/2] 📄 PDF 파일 파싱을 시작합니다. (총 {total_files}개 파일)")
    
    for f_idx, filename in enumerate(pdf_files):
        file_path = os.path.join(folder_path, filename)
        print(f"   -> [{f_idx+1}/{total_files}] 분석 중: {filename}")
        try:
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc, 1):
                text = page.get_text().strip()
                try:
                    tables = page.find_tables()
                    table_texts = []
                    for tab in tables:
                        tab_data = tab.extract()
                        md = table_to_markdown(tab_data)
                        if md:
                            table_texts.append(md)
                    if table_texts:
                        text += "\n\n[표 데이터]\n" + "\n\n".join(table_texts)
                except Exception:
                    pass
                
                if text:
                    page_chunks = splitter.split_text(text)
                    for c_idx, c_text in enumerate(page_chunks):
                        chunks.append({
                            "content": c_text.strip(),
                            "metadata": f"{filename} - {page_num}p (분할 {c_idx+1})"
                        })
            doc.close()
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
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"\n   ⚠️ 트래픽 한도 도달! {retry_delay}초 대기 후 재시도 (시도 {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 1.8
                else:
                    print(f"\n   ❌ 구글 임베딩 API 호출 에러: {e}")
                    return []
        
        if not success:
            print("\n   ❌ 구글 API 트래픽 제한으로 분석이 중단되었습니다.")
            return []
            
        # 유료 티어 속도 향상을 위해 대기시간 단축 (기존 60.0초 -> 0.2초)
        time.sleep(0.2)
            
    return np.array(embeddings_list, dtype=np.float32)

def build_category_cache(category, manuals_root, client, model_name):
    cat_path = os.path.join(manuals_root, category)
    
    # PDF 파일이 아예 없는 폴더는 스캔 대상에서 제외 (불필요한 빌드 방지)
    pdf_files = [f for f in os.listdir(cat_path) if f.lower().endswith('.pdf')]
    if not pdf_files:
        return False
        
    current_hash = get_folder_hash(cat_path, model_name)
    
    # 1. 기존 캐시 파일 로드 및 해시 일치 여부 확인
    db = LocalVectorDB(category)
    if db.load_local(cat_path, current_hash):
        print(f"   ➔ [{category}] 변경 없음 (캐시가 최신 상태입니다. 건너뜀)")
        return False
        
    print(f"\n📂 [{category}] 변경 감지! 벡터 DB 빌드를 시작합니다. (경로: {cat_path})")
    print(f"🔑 폴더 해시: {current_hash}")
    
    # PDF 파싱
    chunks = get_pdf_chunks_cli(cat_path)
    if not chunks:
        print(f"   ⚠️ [{category}] 파싱된 PDF 파일이 없거나 텍스트가 비어 있습니다. 건너뜁니다.")
        return False
        
    # 임베딩 생성
    embeddings = create_embeddings_cli(chunks, client, model_name)
    if embeddings is None or len(embeddings) == 0:
        print(f"   ❌ [{category}] 임베딩 벡터 생성에 실패했습니다.")
        sys.exit(1)
        
    # 로컬 저장
    db.chunks = chunks
    db.embeddings = embeddings
    db.build_index()
    db.save_local(cat_path, current_hash)
    print(f"   🎉 [{category}] 벡터 데이터베이스 빌드 완료! (.vector_cache.pkl)")
    return True

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
    client = genai.Client(api_key=api_key)
    
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
