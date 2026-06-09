import os
import fitz  # PyMuPDF
import streamlit as st

# MuPDF 자체 문법 경고 출력 차단 (터미널 로그 정리)
fitz.TOOLS.mupdf_display_errors(False)

class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size=700, chunk_overlap=80, separators=None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text):
        return self._split_text(text, self.separators)

    def _split_text(self, text, separators):
        final_chunks = []
        if len(text) <= self.chunk_size:
            return [text]
            
        # 사용할 분할 기점(separator) 결정
        separator = separators[-1]
        new_separators = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i+1:]
                break
        
        # 기점 기준 분할
        if separator != "":
            splits = text.split(separator)
        else:
            splits = list(text)
            
        good_splits = []
        for s in splits:
            if s.strip():
                good_splits.append(s)
                
        current_chunk = []
        current_len = 0
        
        for s in good_splits:
            s_len = len(s)
            # 단일 분할 크기가 chunk_size를 초과하면 재귀 분할 진행
            if s_len > self.chunk_size:
                if current_chunk:
                    final_chunks.append(separator.join(current_chunk))
                    current_chunk = []
                    current_len = 0
                
                recursive_chunks = self._split_text(s, new_separators)
                final_chunks.extend(recursive_chunks)
            else:
                sep_len = len(separator) if current_chunk else 0
                if current_len + sep_len + s_len > self.chunk_size:
                    if current_chunk:
                        final_chunks.append(separator.join(current_chunk))
                    
                    # 중첩(Overlap) 구성
                    overlap_chunk = []
                    overlap_len = 0
                    for prev_s in reversed(current_chunk or []):
                        prev_sep_len = len(separator) if overlap_chunk else 0
                        if overlap_len + prev_sep_len + len(prev_s) <= self.chunk_overlap:
                            overlap_chunk.insert(0, prev_s)
                            overlap_len += prev_sep_len + len(prev_s)
                        else:
                            break
                    
                    current_chunk = overlap_chunk
                    current_len = overlap_len
                    
                    sep_len = len(separator) if current_chunk else 0
                    current_chunk.append(s)
                    current_len += sep_len + s_len
                else:
                    current_chunk.append(s)
                    current_len += sep_len + s_len
                    
        if current_chunk:
            final_chunks.append(separator.join(current_chunk))
            
        return final_chunks


def table_to_markdown(table_data):
    if not table_data or len(table_data) < 1:
        return ""
        
    total_cells = 0
    content_cells = 0
    for row in table_data:
        for cell in row:
            total_cells += 1
            if cell is not None and str(cell).strip() != "":
                content_cells += 1
                
    if total_cells > 10:
        density = content_cells / total_cells
        # 텍스트 밀도가 5% 미만인 테이블은 레이아웃 데코레이션이나 빈 그리드 오류로 간주하여 무시
        if density < 0.05:
            return ""
            
    has_content = content_cells > 0
    if not has_content:
        return ""
        
    markdown_lines = []
    max_cols = max(len(row) for row in table_data)
    
    cleaned_table = []
    for row in table_data:
        # ESCAPE PIPE '|' to '\|' inside table cells to protect column boundaries
        cleaned_row = [str(cell or "").replace("\n", " ").replace("|", "\\|").strip() for cell in row]
        cleaned_row += [""] * (max_cols - len(cleaned_row))
        cleaned_table.append(cleaned_row)
    
    markdown_lines.append("| " + " | ".join(cleaned_table[0]) + " |")
    markdown_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in cleaned_table[1:]:
        markdown_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(markdown_lines)


def split_table_markdown(table_md, chunk_size=700, chunk_overlap=80):
    """표 데이터 청크가 chunk_size를 초과하여 쪼개질 경우,
    모든 분할 조각의 상단에 헤더 행(| 항목 | 내용 |) 및 구분선 행을 주입하여 분할"""
    lines = [line.strip() for line in table_md.strip().split("\n") if line.strip()]
    if len(lines) < 2:
        return [table_md]
        
    header_line = lines[0]
    separator_line = lines[1]
    data_lines = lines[2:]
    
    if not data_lines:
        return [table_md]
        
    # 만약 테이블 형태가 아니라면 일반 텍스트 분할 방식과 유사하게 대처
    if not (header_line.startswith("|") and header_line.endswith("|")):
        return [table_md]
        
    chunks = []
    header_part = f"{header_line}\n{separator_line}\n"
    header_len = len(header_part)
    
    current_chunk_lines = [header_line, separator_line]
    current_len = header_len
    
    for row in data_lines:
        row_len = len(row) + 1  # +1 for newline
        # 신규 행 추가 시 크기 초과 여부 확인
        if current_len + row_len > chunk_size:
            if len(current_chunk_lines) > 2:
                chunks.append("\n".join(current_chunk_lines))
                
                # 중첩(Overlap)을 적용하기 위해 이전 청크의 일부 행 가져오기
                overlap_lines = []
                overlap_len = 0
                data_in_chunk = current_chunk_lines[2:]
                for prev_row in reversed(data_in_chunk):
                    if overlap_len + len(prev_row) + 1 <= chunk_overlap:
                        overlap_lines.insert(0, prev_row)
                        overlap_len += len(prev_row) + 1
                    else:
                        break
                        
                current_chunk_lines = [header_line, separator_line] + overlap_lines + [row]
                current_len = header_len + overlap_len + row_len
            else:
                # 단일 행의 길이가 한도를 초과할 경우 예외 처리
                current_chunk_lines.append(row)
                current_len += row_len
        else:
            current_chunk_lines.append(row)
            current_len += row_len
            
    if len(current_chunk_lines) > 2:
        chunks.append("\n".join(current_chunk_lines))
        
    return chunks


def parse_single_pdf(file_path, filename, splitter):
    """단일 PDF 파일을 페이지별로 분석하여 일반 텍스트와 표 텍스트를 독립된 청크로 분리 추출"""
    chunks = []
    doc = fitz.open(file_path)
    
    for page_num, page in enumerate(doc, 1):
        tables = []
        try:
            tables = list(page.find_tables())
        except Exception:
            pass
            
        valid_table_rects = []
        table_texts = []
        for tab in tables:
            try:
                tab_data = tab.extract()
                md = table_to_markdown(tab_data)
                if md:
                    table_texts.append(md)
                    valid_table_rects.append(fitz.Rect(tab.bbox))
            except Exception:
                pass
                
        # 1. 일반 본문 텍스트 추출 (유효한 표 영역을 완전히 제외)
        try:
            blocks = page.get_text("blocks")
            non_table_blocks = []
            for b in blocks:
                rect = fitz.Rect(b[0], b[1], b[2], b[3])
                is_table = False
                for tr in valid_table_rects:
                    intersect = rect & tr
                    if not intersect.is_empty:
                        rect_area = rect.width * rect.height
                        intersect_area = intersect.width * intersect.height
                        if rect_area > 0 and (intersect_area / rect_area) > 0.5:
                            is_table = True
                            break
                if not is_table:
                    non_table_blocks.append(b[4].strip())
            text = "\n\n".join([tb for tb in non_table_blocks if tb])
        except Exception:
            # 에러 발생 시 원본 전체 텍스트 추출로 백업
            text = page.get_text().strip()
            
        page_chunks = []
        
        # 2. 일반 텍스트 분할 및 임포트
        if text.strip():
            page_chunks.extend(splitter.split_text(text))
            
        # 3. 표 데이터 분할 (독립된 원자적 청크로 분리 추출 + 헤더 복원 복사 적용)
        for md in table_texts:
            split_mds = split_table_markdown(md, chunk_size=splitter.chunk_size, chunk_overlap=splitter.chunk_overlap)
            page_chunks.extend(split_mds)
            
        # 4. 무의미한 특수문자 청크 필터링 및 리스트 적재
        for c_idx, c_text in enumerate(page_chunks):
            content_stripped = c_text.strip()
            non_ws = "".join(content_stripped.split())
            if non_ws:
                table_char_count = non_ws.count('|') + non_ws.count('-')
                letters_count = len([char for char in non_ws if char.isalnum()])
                # 청크의 50% 이상이 표 기호이고 한글/영문/숫자 글자수가 15자 미만이면 필터링
                if len(non_ws) > 0 and (table_char_count / len(non_ws) > 0.5) and letters_count < 15:
                    continue
                    
            chunks.append({
                "content": content_stripped,
                "metadata": f"{filename} - {page_num}p (분할 {c_idx+1})"
            })
            
    doc.close()
    return chunks


def parse_single_md(file_path, filename, splitter):
    """단일 Markdown 파일을 읽어 청크로 분할"""
    chunks = []
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if text:
        page_chunks = splitter.split_text(text)
        for c_idx, c_text in enumerate(page_chunks):
            content_stripped = c_text.strip()
            chunks.append({
                "content": content_stripped,
                "metadata": f"{filename} - (분할 {c_idx+1})"
            })
    return chunks


def get_pdf_chunks(folder_path):
    """PDF 또는 MD 파일을 불러와 의미 단위 분할(Recursive Split)하여 추출"""
    chunks = []
    if not os.path.exists(folder_path):
        return chunks
    
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.pdf', '.md'))])
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    # 분석 시 Streamlit 시각화 요소 도입
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_files = len(files)
    if total_files == 0:
        status_text.empty()
        progress_bar.empty()
        return chunks
        
    for f_idx, filename in enumerate(files):
        file_path = os.path.join(folder_path, filename)
        status_text.markdown(f"📄 **문서 분석 중 ({f_idx+1}/{total_files}):** `{filename}`")
        try:
            if filename.lower().endswith('.pdf'):
                file_chunks = parse_single_pdf(file_path, filename, splitter)
                chunks.extend(file_chunks)
            elif filename.lower().endswith('.md'):
                file_chunks = parse_single_md(file_path, filename, splitter)
                chunks.extend(file_chunks)
        except Exception as e:
            st.sidebar.error(f"{filename} 로드 실패: {e}")
        progress_bar.progress(int((f_idx + 1) / total_files * 100))
        
    status_text.empty()
    progress_bar.empty()
    return chunks
