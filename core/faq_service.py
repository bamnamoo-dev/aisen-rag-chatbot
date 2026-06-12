import os
import pickle
import gzip
import time
import numpy as np
from google.genai import types

def load_faq_db(manuals_root="manuals"):
    """manuals/faq_db.pkl 파일을 안전하게 로드합니다. (Gzip 압축 대응)"""
    faq_file = os.path.join(manuals_root, "faq_db.pkl")
    default_db = {"version": "1.0", "faqs": []}
    
    if not os.path.exists(faq_file):
        # 디렉토리가 존재하지 않는다면 자동 생성
        os.makedirs(os.path.dirname(faq_file), exist_ok=True)
        return default_db
        
    try:
        is_gzipped = False
        try:
            with open(faq_file, "rb") as f_test:
                magic = f_test.read(2)
                if magic == b'\x1f\x8b':
                    is_gzipped = True
        except Exception:
            pass
            
        if is_gzipped:
            with gzip.open(faq_file, "rb") as f:
                return pickle.load(f)
        else:
            with open(faq_file, "rb") as f:
                return pickle.load(f)
    except Exception as e:
        print(f"⚠️ FAQ 캐시 로드 실패 (초기값으로 복구): {e}")
        return default_db

def save_faq_db(db, manuals_root="manuals"):
    """FAQ 데이터베이스를 Gzip 압축을 적용하여 로컬에 직렬화 저장합니다."""
    faq_file = os.path.join(manuals_root, "faq_db.pkl")
    os.makedirs(os.path.dirname(faq_file), exist_ok=True)
    try:
        with gzip.open(faq_file, "wb") as f:
            pickle.dump(db, f)
        return True
    except Exception as e:
        print(f"❌ FAQ 캐시 저장 실패: {e}")
        return False

def get_single_embedding(text, client, model_name="gemini-embedding-2"):
    """Google Gemini API를 사용하여 단일 질문의 임베딩 벡터를 구합니다."""
    try:
        response = client.models.embed_content(
            model=model_name,
            contents=types.Content(parts=[types.Part.from_text(text=text)])
        )
        if response.embeddings and len(response.embeddings) > 0:
            return np.array(response.embeddings[0].values, dtype=np.float32)
    except Exception as e:
        print(f"❌ 단일 텍스트 임베딩 생성 오류: {e}")
    return None

def search_faq(query_text, client, model_name="gemini-embedding-2", threshold=0.85, manuals_root="manuals"):
    """
    입력된 질문과 로컬 FAQ DB 내의 질문들 간 코사인 유사도를 계산하여 
    임계값(threshold) 이상인 가장 유사한 FAQ 항목을 리턴합니다.
    """
    db = load_faq_db(manuals_root)
    faqs = db.get("faqs", [])
    
    if not faqs:
        return None, 0.0
        
    # 질문의 임베딩 계산
    query_emb = get_single_embedding(query_text, client, model_name)
    if query_emb is None:
        return None, 0.0
        
    best_faq = None
    best_score = -1.0
    
    # 쿼리 노름 계산 (나누기 대비)
    query_norm = np.linalg.norm(query_emb)
    if query_norm < 1e-10:
        return None, 0.0
        
    for faq in faqs:
        faq_emb = faq.get("embedding")
        if faq_emb is None:
            continue
            
        faq_norm = np.linalg.norm(faq_emb)
        if faq_norm < 1e-10:
            continue
            
        # Cosine Similarity 계산
        score = float(np.dot(query_emb, faq_emb) / (query_norm * faq_norm))
        
        if score > best_score:
            best_score = score
            best_faq = faq
            
    if best_score >= threshold:
        return best_faq, best_score
        
    return None, best_score

def register_faq(question, answer, category, client, model_name="gemini-embedding-2", manuals_root="manuals", recommendations=None):
    """새로운 FAQ(질문-답변 쌍)를 임베딩과 함께 DB에 동적으로 등록합니다."""
    # 질문 임베딩 추출
    embedding = get_single_embedding(question, client, model_name)
    if embedding is None:
        return False
        
    db = load_faq_db(manuals_root)
    
    # 중복 질문 여부 체크 (동일 질문 텍스트 덮어쓰기 또는 중복 배제)
    updated = False
    for faq in db["faqs"]:
        if faq["question"].strip() == question.strip():
            faq["answer"] = answer
            faq["category"] = category
            faq["embedding"] = embedding
            faq["recommendations"] = recommendations or []
            faq["created_at"] = time.time()
            updated = True
            break
            
    if not updated:
        db["faqs"].append({
            "question": question.strip(),
            "answer": answer,
            "category": category,
            "embedding": embedding,
            "recommendations": recommendations or [],
            "created_at": time.time()
        })
        
    return save_faq_db(db, manuals_root)

def delete_faq(question_text, manuals_root="manuals"):
    """질문 텍스트가 일치하는 FAQ 항목을 찾아 DB에서 영구 삭제합니다."""
    db = load_faq_db(manuals_root)
    faqs = db.get("faqs", [])
    
    target_q = question_text.strip()
    original_len = len(faqs)
    new_faqs = [faq for faq in faqs if faq.get("question", "").strip() != target_q]
    
    if len(new_faqs) < original_len:
        db["faqs"] = new_faqs
        return save_faq_db(db, manuals_root)
    return False

def update_faq(old_question, new_question, new_answer, new_category, client, model_name="gemini-embedding-2", manuals_root="manuals"):
    """기존 FAQ 항목을 새로운 질문, 답변, 분야 정보와 함께 업데이트합니다. 질문이 변경된 경우 새로운 임베딩을 구합니다."""
    db = load_faq_db(manuals_root)
    faqs = db.get("faqs", [])
    
    target_idx = -1
    for idx, faq in enumerate(faqs):
        if faq.get("question", "").strip() == old_question.strip():
            target_idx = idx
            break
            
    if target_idx == -1:
        return False
        
    # 질문이 변경된 경우에만 임베딩 새로 생성
    if old_question.strip() == new_question.strip():
        embedding = faqs[target_idx].get("embedding")
    else:
        embedding = get_single_embedding(new_question, client, model_name)
        if embedding is None:
            return False
            
    faqs[target_idx] = {
        "question": new_question.strip(),
        "answer": new_answer,
        "category": new_category,
        "embedding": embedding,
        "recommendations": faqs[target_idx].get("recommendations", []),
        "created_at": time.time()
    }
    
    return save_faq_db(db, manuals_root)

def sync_faq_to_github(manuals_root="manuals"):
    """
    로컬의 FAQ 데이터베이스 파일(faq_db.pkl)을 깃허브 원격 저장소에 자동으로 커밋&푸시하여
    웹 서버와 실시간으로 동기화합니다.
    """
    import subprocess
    faq_file = os.path.join(manuals_root, "faq_db.pkl")
    
    if not os.path.exists(faq_file):
        return False, "FAQ 데이터베이스 파일이 존재하지 않습니다."
        
    try:
        status_res = subprocess.run(["git", "status", "--porcelain", faq_file], capture_output=True, text=True, check=True)
        if not status_res.stdout.strip():
            return True, "변경 사항이 없어 동기화가 필요하지 않습니다. (이미 최신 상태)"
            
        subprocess.run(["git", "add", faq_file], capture_output=True, text=True, check=True)
        subprocess.run(["git", "commit", "-m", "Admin: Update FAQ database via dashboard sync"], capture_output=True, text=True, check=True)
        subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True, check=True)
        
        return True, "성공적으로 깃허브 원격 서버와 동기화가 완료되었습니다!"
        
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr if e.stderr else str(e)
        return False, f"Git 명령 실행 오류: {err_msg.strip()}"
    except Exception as e:
        return False, f"동기화 에러: {str(e)}"



