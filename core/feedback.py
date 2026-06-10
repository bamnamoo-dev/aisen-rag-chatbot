import os
import csv
from datetime import datetime

class FeedbackManager:
    CSV_FILE_NAME = "feedback.csv"

    @classmethod
    def get_csv_path(cls, manuals_root="manuals"):
        """피드백 CSV 파일의 절대 경로를 반환합니다. sync.bat와 웹 대시보드가 읽을 수 있도록 manuals 내에 보관합니다."""
        # manuals_root가 프로젝트 루트 기준 상대경로 또는 절대경로일 수 있으므로 유연하게 매핑
        return os.path.join(manuals_root, cls.CSV_FILE_NAME)

    @classmethod
    def save_feedback(cls, category, question, answer, feedback_type, comment="", referenced_files=None, manuals_root="manuals"):
        """
        사용자의 👍/👎 피드백 데이터를 manuals/feedback.csv 파일에 누적하여 저장합니다.
        
        Args:
            category (str): 질문 카테고리 (예: 계약, 감사 등)
            question (str): 사용자 질문 내용
            answer (str): 챗봇이 출력한 답변
            feedback_type (str): 'like' (좋아요) 또는 'dislike' (싫어요)
            comment (str): 싫어요 선택 시 작성한 추가 불만족/수정 요청 사유
            referenced_files (list or str): 답변에 참조된 지침 파일명 리스트
            manuals_root (str): manuals 폴더 경로
        """
        csv_path = cls.get_csv_path(manuals_root)
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        
        # 참조 파일 리스트 문자열 변환
        if isinstance(referenced_files, list):
            referenced_files_str = ", ".join(referenced_files)
        else:
            referenced_files_str = referenced_files if referenced_files else ""

        # CSV 파일에 기록할 한 행 데이터 정의
        row_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category,
            question.strip(),
            answer.strip(),
            feedback_type,
            comment.strip(),
            referenced_files_str
        ]

        file_exists = os.path.exists(csv_path)

        # 동시 쓰기 시 발생할 수 있는 락(Lock)을 방지하기 위한 안전장치 추가 및 utf-8-sig 인코딩으로 엑셀 한글 깨짐 방지
        try:
            with open(csv_path, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                if not file_exists:
                    # 파일이 없을 시 헤더 행 추가
                    writer.writerow([
                        "Timestamp", "Category", "Question", "Answer", 
                        "FeedbackType", "Comment", "ReferencedFiles"
                    ])
                writer.writerow(row_data)
            return True
        except Exception as e:
            # 콘솔에 오류 기록
            print(f"❌ 피드백 CSV 저장 실패: {e}")
            return False
            
    @classmethod
    def load_feedbacks(cls, manuals_root="manuals"):
        """저장된 피드백 목록을 역순(최신순) 리스트로 읽어옵니다. 대시보드 뷰어용 기능."""
        csv_path = cls.get_csv_path(manuals_root)
        if not os.path.exists(csv_path):
            return []
            
        feedbacks = []
        try:
            with open(csv_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    feedbacks.append(row)
            # 최신 피드백이 가장 위에 보이도록 역순 정렬
            feedbacks.reverse()
        except Exception as e:
            print(f"❌ 피드백 CSV 로드 실패: {e}")
        return feedbacks
