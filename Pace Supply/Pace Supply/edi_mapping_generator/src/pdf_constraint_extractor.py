"""
PDF Constraint Extractor Module.
Uses AI to parse Vendor Implementation Guide PDF and extract structural constraints.
"""
import json
from typing import Dict, Any, List
from .ai_client import AIClient
from .logger import get_logger
from .pdf_extractor import extract_text_from_pdf

class PdfConstraintExtractor:
    """Extracts EDI constraints from PDF specifications."""
    
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.logger = get_logger()
        
    def extract_constraints(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract constraints from the PDF file.
        
        Returns:
            Dictionary containing extracted constraints:
            {
                "segments": {
                    "BEG": {"req": "M", "elements": {"02": ["NE"]}},
                    ...
                }
            }
        """
        self.logger.info(f"Extracting constraints from PDF: {pdf_path}")
        
        # 1. Extract text
        try:
            pdf_text = extract_text_from_pdf(pdf_path)
        except Exception as e:
            self.logger.error(f"Failed to read PDF: {e}")
            return {}

        # 2. Chunking (if needed, but assuming small enough for now or taking first few pages for headers and definition)
        # Ideally we process the whole thing. If it's huge, we might need a strategy.
        # For this task, we'll try to fit reasonable amount.
        # "partner_spec.pdf" is likely readable.
        
        # Truncate if too long (approx 100k chars ~ 25k tokens).
        if len(pdf_text) > 100000:
            self.logger.warning("PDF text too long, truncating to first 100k chars")
            pdf_text = pdf_text[:100000]
            
        # 3. Constraint extraction prompt
        prompt = self._build_constraint_prompt(pdf_text)
        
        # 4. Call AI
        try:
            response = self.ai_client.get_completion(
                prompt, 
                system_prompt="You are an Expert Technical Specification Analyst. Your job is to extract strict validation rules (Knowledge Base) from vendor PDFs."
            )
            
            # 5. Parse JSON
            constraints = self._parse_json(response)
            self.logger.info(f"Extracted constraints for {len(constraints.get('segments', {}))} segments")
            return constraints
            
        except Exception as e:
            self.logger.error(f"Error extracting constraints: {e}")
            return {"segments": {}}

    def _build_constraint_prompt(self, pdf_text: str) -> str:
        return f"""
Analyze the following EDI Implementation Guide (PDF Content) to build a "Rules Knowledge Base".

## DOC TEXT:
{pdf_text}

## GOAL:
Extract a JSON object summarizing constraints for segments and elements.
Focus on:
1. Mandatory Segments (Requirement = "M" or "Mandatory")
2. Allowed Values for specific elements (e.g. "BEG01 must be '00'")
3. Usage rules (e.g. "REF*DP" is required)

## OUTPUT FORMAT:
JSON only.
{{
  "segments": {{
    "SEGMENT_ID": {{
        "req": "M" or "O",
        "elements": {{
            "INDEX": {{ "values": ["VAL1", "VAL2"] }} 
        }}
    }}
  }}
}}

Example:
{{
  "segments": {{
    "BEG": {{
      "req": "M",
      "elements": {{
        "01": {{ "values": ["00"] }},
        "02": {{ "values": ["NE", "DS"] }}
      }}
    }},
    "DTM": {{
      "req": "O",
      "elements": {{
        "01": {{ "values": ["002", "010"] }}
      }}
    }}
  }}
}}

Ignore pure formatting or boilerplate text. Return ONLY the JSON.
"""

    def _parse_json(self, response: str) -> Dict[str, Any]:
        """Helper to parse JSON from AI response."""
        try:
            # Clean markdown
            if "```" in response:
                response = response.split("```json")[-1].split("```")[0].strip()
            if "```" in response: # fallback
                response = response.strip("`")
                
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                response = response[start:end+1]
                
            return json.loads(response)
        except Exception as e:
            self.logger.warning(f"JSON Parsing failed: {e}")
            return {"segments": {}}
