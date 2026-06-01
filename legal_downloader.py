import os
import sys
import urllib.request
import urllib.parse

# Reconfigure stdout/stderr encoding to UTF-8 for Windows console support
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# 1. 다운로드할 교육행정 핵심 중앙 법령 리스트 (legalize-kr 저장소 연계)
CORE_TARGETS = [
    {
        "name": "지방공무원법",
        "repo": "legalize-kr",
        "path": "kr/지방공무원법/법률.md",
        "filename": "지방공무원법.md"
    },
    {
        "name": "지방공무원 임용령",
        "repo": "legalize-kr",
        "path": "kr/지방공무원임용령/대통령령.md",
        "filename": "지방공무원_임용령.md"
    },
    {
        "name": "지방공무원 복무규정",
        "repo": "legalize-kr",
        "path": "kr/지방공무원복무규정/대통령령.md",
        "filename": "지방공무원_복무규정.md"
    },
    {
        "name": "지방공무원 수당등에 관한 규정",
        "repo": "legalize-kr",
        "path": "kr/지방공무원수당등에관한규정/대통령령.md",
        "filename": "지방공무원_수당규정.md"
    },
    {
        "name": "지방자치단체를 당사자로 하는 계약에 관한 법률",
        "repo": "legalize-kr",
        "path": "kr/지방자치단체를당사자로하는계약에관한법률/법률.md",
        "filename": "지방계약법.md"
    },
    {
        "name": "지방자치단체를 당사자로 하는 계약에 관한 법률 시행령",
        "repo": "legalize-kr",
        "path": "kr/지방자치단체를당사자로하는계약에관한법률/시행령.md",
        "filename": "지방계약법_시행령.md"
    },
    {
        "name": "지방자치단체를 당사자로 하는 계약에 관한 법률 시행규칙",
        "repo": "legalize-kr",
        "path": "kr/지방자치단체를당사자로하는계약에관한법률/시행규칙.md",
        "filename": "지방계약법_시행규칙.md"
    },
    {
        "name": "지방재정법",
        "repo": "legalize-kr",
        "path": "kr/지방재정법/법률.md",
        "filename": "지방재정법.md"
    },
    {
        "name": "지방재정법 시행령",
        "repo": "legalize-kr",
        "path": "kr/지방재정법/시행령.md",
        "filename": "지방재정법_시행령.md"
    },
    {
        "name": "지방회계법",
        "repo": "legalize-kr",
        "path": "kr/지방회계법/법률.md",
        "filename": "지방회계법.md"
    },
    {
        "name": "지방회계법 시행령",
        "repo": "legalize-kr",
        "path": "kr/지방회계법/시행령.md",
        "filename": "지방회계법_시행령.md"
    },
    {
        "name": "초ㆍ중등교육법",
        "repo": "legalize-kr",
        "path": "kr/초ㆍ중등교육법/법률.md",
        "filename": "초중등교육법.md"
    },
    {
        "name": "초ㆍ중등교육법 시행령",
        "repo": "legalize-kr",
        "path": "kr/초ㆍ중등교육법/시행령.md",
        "filename": "초중등교육법_시행령.md"
    },
    {
        "name": "초ㆍ중등교육법 시행규칙",
        "repo": "legalize-kr",
        "path": "kr/초ㆍ중등교육법/시행규칙.md",
        "filename": "초중등교육법_시행규칙.md"
    },
    {
        "name": "개인정보 보호법",
        "repo": "legalize-kr",
        "path": "kr/개인정보보호법/법률.md",
        "filename": "개인정보보호법.md"
    }
]

# 2. 로컬 자치법규 및 기타 규정 텍스트 빌드 (서울시교육청 특화 RAG용 구조화 마크다운)
LOCAL_STATUTES = [
    {
        "filename": "서울시교육청_지방공무원_복무조례.md",
        "name": "서울특별시교육감 소속 지방공무원 복무 조례",
        "content": """# 서울특별시교육감 소속 지방공무원 복무 조례

## 제1조 (목적)
이 조례는 「지방공무원법」 제59조에 따라 서울특별시교육감 소속 지방공무원의 복무에 관하여 필요한 사항을 규정함을 목적으로 한다.

## 제13조 (경조사 휴가)
공무원은 본인의 결혼이나 기타 경조사가 있을 경우 아래의 기준에 따라 특별휴가를 얻을 수 있다.
- 본인의 결혼: 5일
- 자녀의 결혼: 1일
- 배우자의 출산: 10일
- 배우자 또는 본인/배우자의 부모 사망: 5일
- 본인 및 배우자의 조부모/외조부모 사망: 3일
- 자녀 또는 그 자녀의 배우자 사망: 3일

## 제16조 (장기재직휴가)
소속 기관의 장은 재직기간이 다음 각 호에 해당하는 공무원에게 해당 기간 중 장기재직휴가를 허가할 수 있다. 이 경우 재직기간 산정은 「지방공무원 복무규정」 제7조제2항에 따른다.
1. 재직기간 5년 이상 10년 미만: 5일
2. 재직기간 10년 이상 18년 미만: 10일
3. 재직기간 18년 이상 25년 미만: 15일
4. 재직기간 25년 이상: 20일
※ 사용하지 않은 휴가는 이월되거나 저축할 수 없으며 소멸된다. 재직기간별 휴가일수가 10일 이하인 경우 3회 이내로, 10일을 초과하는 경우 6회 이내로 분할 사용할 수 있으며 매회 사용 일수는 3일 이상이어야 한다.

## 제17조 (특별휴가 - 기타)
- **학습휴가**: 공무원은 재직기간 중 자기개발을 위하여 연 5일의 학습휴가를 얻을 수 있다. (기존 4일에서 5일로 확대)
- **포상휴가**: 업무를 성공적으로 수행하여 탁월한 성과와 공로가 인정되는 경우 5일 이내의 포상휴가를 얻을 수 있다. 공로에 대한 판단 기준은 교육감이 따로 정한다.
- **자녀돌봄휴가**: 공무원은 자녀가 있는 경우 다음 각 호의 어느 하나에 해당할 때 연 2일(자녀가 2명 이상이거나 장애인 자녀인 경우 3일)의 범위에서 자녀돌봄휴가를 얻을 수 있다.
  1. 어린이집, 유치원, 학교의 공식 행사 참여
  2. 교사 상담
  3. 예방접종 또는 병원 진료 시 동행
"""
    },
    {
        "filename": "서울시_교육비특별회계_재무회계규칙.md",
        "name": "서울특별시 교육비특별회계 재무회계 규칙",
        "content": """# 서울특별시 교육비특별회계 재무회계 규칙

## 제1조 (목적)
이 규칙은 「지방회계법 시행령」에 따라 서울특별시 교육비특별회계의 예산·결산 및 회계관리에 관하여 필요한 사항을 규정함을 목적으로 한다.

## 제3조 (회계관계공무원의 관직지정)
교육비특별회계의 예산 및 회계 처리를 총괄하기 위해 지정하는 명령기관과 출납기관은 다음과 같다.
- **징수관**: 본청은 행정국장(또는 재정 담당 국장), 교육지원청은 교육지원국장(또는 재정 지원 부서장).
- **재무관**: 본청은 재정과장(또는 재무 담당 부서장), 교육지원청은 행정지원과장(또는 예산 계약 담당 부서장).
- **지출원**: 본청은 재무 담당 팀장, 교육지원청은 예산 계약 담당 팀장.
- **분임징수관/분임재무관**: 일선 학교(제2관서)의 경우 학교장(교육기관의 장)이 분임징수관 및 분임재무관으로 임명된다.
- **일상경비출납원/수입금출납원**: 일선 학교의 행정실장이 일상경비 및 수입금 출납원으로서 출납 업무를 담당한다.

## 제25조 (지출원인행위)
1. 재무관(학교의 경우 분임재무관인 학교장)은 예산의 범위에서 지출의 원인이 되는 계약이나 결정을 하는 지출원인행위를 하여야 한다.
2. 지출원인행위를 할 때에는 지출원인행위서(지출결의서)를 작성하고 계약금액, 지급방법, 지급상대방 등을 명확히 기재하여 결재를 받아야 한다.

## 제50조 (학교 예산 전용 및 이월)
1. 학교장은 교육과정 운영상 불가피한 경우 예산의 세항, 목 간 금액을 전용할 수 있으며, 이 경우 분임재무관의 결재를 받아 전용 내역을 관리해야 한다.
2. 세출예산 중 연도 내에 지출하지 못한 예산은 이월하여 다음 연도에 사용할 수 있으며, 명시이월과 사고이월로 구분하여 의회의 승인 또는 학교운영위원회의 심의를 거쳐 처리한다.
"""
    },
    {
        "filename": "지방자치단체_회계관리에관한규칙.md",
        "name": "지방자치단체 회계관리에 관한 규칙 (훈령)",
        "content": """# 지방자치단체 회계관리에 관한 규칙 (훈령)

## 제1조 (목적)
이 규칙(훈령)은 「지방회계법」 및 같은 법 시행령에서 위임된 사항과 지방자치단체의 예산, 결산, 기금 및 회계 관리에 필요한 세부 기준을 정함을 목적으로 한다.

## 제15조 (세출예산의 지출원칙)
1. 지출원은 세출예산의 범위에서 정당한 채권자에게 지출하여야 한다.
2. 모든 지출은 법정 서식인 지출결의서에 의하여 처리되어야 하며, 지출원인행위서와 연계되어 관리되어야 한다.

## 제22조 (수의계약 기준 및 금액 한도)
지방자치단체의 장 또는 계약담당공무원은 다음 각 호의 금액 한도 이하인 경우 수의계약을 체결할 수 있다.
- **일반 용역 및 물품 구매**: 2천만 원 이하 (여성기업, 장애인기업, 사회적기업 등의 경우 5천만 원 이하).
- **공사**: 종합공사 4천만 원 이하, 전문공사 2천만 원 이하.
- **천재지변 등 비상재해**: 제한 없이 수의계약 가능.

## 제35조 (회계 증빙서류 보관 및 제출)
1. 회계관계공무원은 모든 지출 및 수입에 대한 증빙서류(세금계산서, 카드영수증, 검수조서 등)의 원본을 5년간 보관하여야 한다.
2. 전자적 회계시스템(K-에듀파인 등)에 등록된 전자 서명 및 증빙 데이터는 원본 증빙서류와 동일한 효력을 가진다.
"""
    },
    {
        "filename": "행정효율_및_협업촉진에관한규정.md",
        "name": "행정 효율과 협업 촉진에 관한 규정 (대통령령)",
        "content": """# 행정 효율과 협업 촉진에 관한 규정 (대통령령)

## 제1조 (목적)
이 영은 행정기관의 행정업무의 운영 및 협업 촉진에 필요한 사항을 규정함으로써 행정의 효율성을 높이고 협업 문화를 조성함을 목적으로 한다.

## 제10조 (공문서의 분류)
행정기관이 생산하거나 접수하는 공문서는 다음과 같이 분류한다.
1. **지시문서**: 훈령, 지시, 예규, 일일명령 등 행정기관이 하급기관이나 소속 공무원에 대하여 지시하는 문서.
2. **공고문서**: 고시, 공고 등 행정기관이 일정한 사항을 일반에게 알리는 문서.
3. **일반문서**: 위의 분류에 속하지 않는 일반적인 기안문, 보고서, 협조문 등.

## 제15조 (기안 및 결재 절차)
1. 문서의 기안은 전자문서시스템을 사용하여 전자문서로 기안하는 것을 원칙으로 한다.
2. 기안자는 기안문서에 대하여 과장, 국장 등 결재권자의 서명이나 전자서명을 받아 결재를 득하여야 효력이 발생한다.
3. 결재권자가 출장 등의 사유로 결재할 수 없을 때에는 대결(대리결재)을 하되, 중요 문서의 경우 사후에 보고하여야 한다.

## 제22조 (관인의 날인 및 서명)
행정기관의 장의 명의로 발신하는 문서에는 관인을 찍거나 기관장의 서명(전자이미지서명 포함)을 하여야 한다. 다만, 경미한 내용의 문서나 보고서 등은 날인 또는 서명을 생략할 수 있으며, 이 경우 '날인생략' 또는 '서명생략'을 표시한다.
"""
    }
]

def url_encode_path(path):
    parts = path.split('/')
    encoded_parts = [urllib.parse.quote(part) for part in parts]
    return '/'.join(encoded_parts)

def download_core_laws(dest_dir="manuals/조례규칙"):
    os.makedirs(dest_dir, exist_ok=True)
    print(f"📥 법령/조례 데이터베이스 빌드를 시작합니다... (저장 경로: {dest_dir})\n")
    
    success_count = 0
    
    # 1. 중앙 법령 다운로드
    print("--- [1/2] 🏛️ 중앙 정부 법령/시행령/규칙 다운로드 (GitHub raw) ---")
    for target in CORE_TARGETS:
        repo = target["repo"]
        path = target["path"]
        filename = target["filename"]
        name = target["name"]
        
        encoded_path = url_encode_path(path)
        raw_url = f"https://raw.githubusercontent.com/legalize-kr/{repo}/main/{encoded_path}"
        
        print(f" -> '{name}' 다운로드 중...")
        try:
            req = urllib.request.Request(
                raw_url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                
            dest_path = os.path.join(dest_dir, filename)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            file_size_kb = os.path.getsize(dest_path) / 1024
            print(f"    ✅ 성공: {filename} ({file_size_kb:.1f} KB) 저장 완료.")
            success_count += 1
        except Exception as e:
            print(f"    ❌ 실패: {name} 다운로드 중 오류 발생 -> {e}")
            
    # 2. 로컬 자치법규 빌드 및 저장
    print("\n--- [2/2] ⚖️ 서울시교육청 자치조례 및 회계 실무 훈령/규칙 생성 ---")
    for local in LOCAL_STATUTES:
        filename = local["filename"]
        name = local["name"]
        content = local["content"]
        
        print(f" -> '{name}' 데이터 생성 중...")
        try:
            dest_path = os.path.join(dest_dir, filename)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content.strip())
                
            file_size_kb = os.path.getsize(dest_path) / 1024
            print(f"    ✅ 성공: {filename} ({file_size_kb:.1f} KB) 작성 완료.")
            success_count += 1
        except Exception as e:
            print(f"    ❌ 실패: {name} 파일 작성 중 오류 발생 -> {e}")
            
    total_expected = len(CORE_TARGETS) + len(LOCAL_STATUTES)
    print(f"\n🎉 법령/조례 데이터베이스 빌드 완료! (성공: {success_count}/{total_expected}개)")

if __name__ == "__main__":
    download_core_laws()
