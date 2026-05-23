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
            
    return np.array(embeddings_list)

def main():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 에러: .env 파일에 GOOGLE_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)
        
    manuals_root = "manuals"
    
    # 카테고리 입력 받기
    if len(sys.argv) < 2:
        # 폴더 목록 보여주기
        if not os.path.exists(manuals_root):
            print(f"❌ 에러: {manuals_root} 폴더가 존재하지 않습니다.")
            sys.exit(1)
        categories = sorted([d for d in os.listdir(manuals_root) if os.path.isdir(os.path.join(manuals_root, d))])
        print("사용 가능한 카테고리 목록:")
        for idx, cat in enumerate(categories):
            print(f"  {idx + 1}. {cat}")
        
        try:
            choice = input("\n분석할 카테고리 번호 또는 이름을 입력하세요: ").strip()
            if not choice:
                print("입력이 없습니다. 종료합니다.")
                sys.exit(0)
            if choice.isdigit() and 1 <= int(choice) <= len(categories):
                category = categories[int(choice) - 1]
            else:
                category = choice
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            sys.exit(0)
    else:
        category = sys.argv[1]
        
    cat_path = os.path.join(manuals_root, category)
    if not os.path.exists(cat_path):
        print(f"❌ 에러: '{cat_path}' 폴더가 존재하지 않습니다.")
        sys.exit(1)
        
    model_name = "gemini-embedding-2"
    client = genai.Client(api_key=api_key)
    
    # 해시 계산
    current_hash = get_folder_hash(cat_path, model_name)
    print(f"📂 카테고리: {category} (경로: {cat_path})")
    print(f"🔑 폴더 해시: {current_hash}")
    
    # PDF 파싱
    chunks = get_pdf_chunks_cli(cat_path)
    if not chunks:
        print("❌ 파싱된 텍스트가 없습니다. PDF 파일이 있는지 확인해 주세요.")
        sys.exit(1)
        
    # 임베딩 생성
    embeddings = create_embeddings_cli(chunks, client, model_name)
    if embeddings is None or len(embeddings) == 0:
        print("❌ 임베딩 벡터 생성에 실패했습니다.")
        sys.exit(1)
        
    # LocalVectorDB 객체 생성 및 로컬 저장
    db = LocalVectorDB(category)
    db.chunks = chunks
    db.embeddings = embeddings
    db.build_index()
    db.save_local(cat_path, current_hash)
    
    print(f"🎉 성공: '{category}' 카테고리의 벡터 데이터베이스 빌드 완료!")
    print(f"💾 저장 위치: {os.path.join(cat_path, '.vector_cache.pkl')}")

if __name__ == "__main__":
    main()
