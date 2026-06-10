import os
from core.feedback import FeedbackManager

def test_feedback_system():
    print("=== 피드백 시스템 오프라인 테스트 ===")
    manuals_root = "manuals"
    csv_path = FeedbackManager.get_csv_path(manuals_root)
    
    # 1. 기존 테스트 피드백 파일 제거 (깨끗한 테스트 환경 조성)
    if os.path.exists(csv_path):
        os.remove(csv_path)
        print("이전 테스트 feedback.csv 파일 제거 완료.")

    # 2. 피드백 저장 테스트 1 (좋아요)
    print("\n1. 좋아요 피드백 저장 테스트...")
    res1 = FeedbackManager.save_feedback(
        category="계약",
        question="S2B 수의계약 한도가 어떻게 되나요?",
        answer="종합공사는 4억원 이하, 전문공사는 2억원 이하입니다.",
        feedback_type="like",
        referenced_files=["1.서울특별시교육청 계약업무 처리지침 - 5p", "1.서울특별시교육청 계약업무 처리지침 - 6p"],
        manuals_root=manuals_root
    )
    print(f"저장 성공 여부: {res1}")

    # 3. 피드백 저장 테스트 2 (싫어요 + 코멘트)
    print("\n2. 싫어요 및 상세 사유 피드백 저장 테스트...")
    res2 = FeedbackManager.save_feedback(
        category="감사",
        question="학교 자율 감사 주기는 어떻게 되나요?",
        answer="학교 자율 감사 주기는 매년 1회 실시해야 합니다.",
        feedback_type="dislike",
        comment="자율 감사는 2년에 1회 실시하는 것이 맞습니다. 지침서 내용이 잘못 분석되었습니다.",
        referenced_files=["2026년 학교자율 종합감사 운영매뉴얼 - 12p"],
        manuals_root=manuals_root
    )
    print(f"저장 성공 여부: {res2}")

    # 4. 파일 존재 여부 및 인코딩 확인
    print(f"\n3. 생성된 CSV 파일 경로: {csv_path}")
    print(f"파일 존재 여부: {os.path.exists(csv_path)}")
    if os.path.exists(csv_path):
        print(f"파일 크기: {os.path.getsize(csv_path)} bytes")

    # 5. 피드백 로드 테스트
    print("\n4. 피드백 최신순 로딩 테스트...")
    feedbacks = FeedbackManager.load_feedbacks(manuals_root)
    print(f"로드된 피드백 개수: {len(feedbacks)}개")
    for i, fb in enumerate(feedbacks):
        print(f"\n[{i+1}] {fb['Timestamp']} | 카테고리: {fb['Category']} | 평가: {fb['FeedbackType']}")
        print(f"질문: {fb['Question']}")
        print(f"답변: {fb['Answer'][:50]}...")
        if fb['Comment']:
            print(f"상세 사유: {fb['Comment']}")
        print(f"참조 지침서: {fb['ReferencedFiles']}")

if __name__ == "__main__":
    test_feedback_system()
