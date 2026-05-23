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
        cleaned_row = [str(cell or "").replace("\n", " ").strip() for cell in row]
        cleaned_row += [""] * (max_cols - len(cleaned_row))
        cleaned_table.append(cleaned_row)
    
    markdown_lines.append("| " + " | ".join(cleaned_table[0]) + " |")
    markdown_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in cleaned_table[1:]:
        markdown_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(markdown_lines)


def get_pdf_chunks(folder_path):
    """PDF 파일을 페이지 단위로 불러와 의미 단위 분할(Recursive Split) 및 표 데이터 보존하여 추출"""
    chunks = []
    if not os.path.exists(folder_path):
        return chunks
    
    pdf_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')])
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)
    
    # 분석 시 시각화 요소 도입
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_files = len(pdf_files)
    for f_idx, filename in enumerate(pdf_files):
        file_path = os.path.join(folder_path, filename)
        status_text.markdown(f"📄 **PDF 분석 중 ({f_idx+1}/{total_files}):** `{filename}`")
        try:
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc, 1):
                # 1. 일반 텍스트 추출
                text = page.get_text().strip()
                
                # 2. 표 데이터 추출 및 마크다운 보존
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
                        content_stripped = c_text.strip()
                        # 무의미하게 표 기호(|)와 공백만 가득한 청크 필터링 (글자 수가 너무 적은 경우 제외)
                        non_ws = "".join(content_stripped.split())
                        if non_ws:
                            table_char_count = non_ws.count('|') + non_ws.count('-')
                            letters_count = len([char for char in non_ws if char.isalnum()])
                            # 청크의 50% 이상이 표 기호이고, 실제 한글/영어/숫자 글자수가 15자 미만이면 무시
                            if len(non_ws) > 0 and (table_char_count / len(non_ws) > 0.5) and letters_count < 15:
                                continue
                                
                        chunks.append({
                            "content": content_stripped,
                            "metadata": f"{filename} - {page_num}p (분할 {c_idx+1})"
                        })
            doc.close()
        except Exception as e:
            st.sidebar.error(f"{filename} 로드 실패: {e}")
        progress_bar.progress(int((f_idx + 1) / total_files * 100))
        
    status_text.empty()
    progress_bar.empty()
    return chunks
