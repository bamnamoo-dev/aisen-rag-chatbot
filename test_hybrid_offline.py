import sys
import os
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.vector_db import LocalVectorDB, simple_korean_tokenizer, retrieve_top_chunks

def test_tokenizer():
    print("=== 토크나이저 테스트 ===")
    test_queries = [
        "제30조 수의계약",
        "S2B 4억원",
        "지방계약법 시행령 제30조의2 수의계약에 대하여 알려줘"
    ]
    for q in test_queries:
        tokens = simple_korean_tokenizer(q)
        print(f"Query: '{q}' -> Tokens: {tokens}")

def test_db_loading_and_bm25():
    print("\n=== 벡터 캐시 로드 및 BM25 테스트 ===")
    category = "계약"
    manuals_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuals")
    cat_path = os.path.join(manuals_root, category)
    
    # 1. LocalVectorDB 인스턴스 생성
    db = LocalVectorDB(category)
    
    # 2. 캐시 로드 (원래 hash를 전달해야 하나, 여기서는 load_local 내부에서 hash 비교를 통과하게 하기 위해 현재 폴더의 해시를 구함)
    from core.vector_db import get_folder_hash
    current_hash = get_folder_hash(cat_path, "gemini-embedding-2")
    
    print(f"계약 카테고리 폴더 해시: {current_hash}")
    success = db.load_local(cat_path, current_hash)
    print(f"로컬 캐시 로드 결과: {success}")
    
    if success:
        print(f"로드된 청크 수: {len(db.chunks)}")
        print(f"임베딩 로드 여부: {db.embeddings is not None}")
        if db.embeddings is not None:
            print(f"임베딩 Shape: {db.embeddings.shape}")
        print(f"FAISS 인덱스 로드 여부: {db.index is not None}")
        print(f"BM25 인덱스 생성 여부: {db.bm25 is not None}")
        
        # 3. 로컬 BM25 스코어 테스트 (구글 API 호출 없이 BM25 검색이 잘 작동하는지 확인)
        query = "S2B"
        query_tokens = simple_korean_tokenizer(query)
        if db.bm25 and query_tokens:
            scores = db.bm25.get_scores(query_tokens)
            max_idx = np.argmax(scores)
            max_score = scores[max_idx]
            print(f"BM25 테스트 쿼리: '{query}'")
            print(f"최고 매칭 문서 인덱스: {max_idx}, 점수: {max_score}")
            print(f"최고 매칭 문서 본문 일부: {db.chunks[max_idx]['content'][:150]}...")
            print(f"최고 매칭 문서 메타데이터: {db.chunks[max_idx]['metadata']}")
            
            # 상위 5개 결과 출력
            top_indices = np.argsort(scores)[::-1][:5]
            print("\nBM25 상위 5개 매칭 결과:")
            for i, idx in enumerate(top_indices):
                if scores[idx] > 0:
                    print(f"{i+1}. [점수: {scores[idx]:.4f}] {db.chunks[idx]['metadata']} | 본문: {db.chunks[idx]['content'][:100]}...")
        else:
            print("BM25 인덱스가 활성화되지 않았거나 토큰이 없습니다.")

if __name__ == "__main__":
    test_tokenizer()
    test_db_loading_and_bm25()
