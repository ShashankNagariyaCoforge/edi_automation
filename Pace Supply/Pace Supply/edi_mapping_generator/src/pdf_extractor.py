"""
PDF text extraction module.
"""
import fitz  # PyMuPDF
from pathlib import Path
from logger import get_logger


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text content from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        Full text content of the PDF
    
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        Exception: If PDF cannot be read
    """
    logger = get_logger()
    pdf_file = Path(pdf_path)
    
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    logger.info(f"Extracting text from PDF: {pdf_file.name}")
    
    try:
        doc = fitz.open(str(pdf_file))
        text_content = []
        page_count = len(doc)
        
        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            text_content.append(f"--- Page {page_num + 1} ---\n{page_text}")
            logger.debug(f"Extracted page {page_num + 1}/{page_count}")
        
        doc.close()
        
        full_text = "\n\n".join(text_content)
        logger.info(f"Extracted {page_count} pages, {len(full_text)} characters")
        
        return full_text
    
    except Exception as e:
        logger.error(f"Failed to extract PDF: {e}")
        raise


def get_pdf_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF."""
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count
