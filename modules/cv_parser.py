"""
CV Parser Module
Supports: PDF, DOCX, DOC
Extracts plain text from uploaded CV files.
"""

import os


def parse_cv(filepath: str) -> str:
    """
    Parse CV file and return extracted text.
    Supports PDF and DOCX formats.
    """
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".pdf":
            return _parse_pdf(filepath)
        elif ext in (".docx", ".doc"):
            return _parse_docx(filepath)
        else:
            return ""
    except Exception as e:
        print(f"[CV Parser] Error parsing {filepath}: {e}")
        return ""


def _parse_pdf(filepath: str) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except ImportError:
        # Fallback to PyPDF2
        try:
            import PyPDF2
            text = ""
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            print(f"[CV Parser] PDF fallback error: {e}")
            return ""


def _parse_docx(filepath: str) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
        doc  = Document(filepath)
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        return text.strip()
    except Exception as e:
        print(f"[CV Parser] DOCX error: {e}")
        return ""


def get_cv_summary(cv_text: str, max_chars: int = 500) -> str:
    """Return a short summary of CV text for display."""
    if not cv_text:
        return "CV text available nahi hai."
    return cv_text[:max_chars] + ("..." if len(cv_text) > max_chars else "")
