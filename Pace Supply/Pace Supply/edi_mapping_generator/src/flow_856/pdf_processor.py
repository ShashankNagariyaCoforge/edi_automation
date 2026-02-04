import json
from typing import Dict, Any, List
from ai_client import AIClient
from logger import get_logger
from pdf_extractor import extract_text_from_pdf

class PdfProcessor856:
    """
    Specialized PDF Processor for 856 (ASN) Flow.
    Extracts Mandatory Segments and 'Must Use' fields using AI.
    """
    
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.logger = get_logger()

    def extract_mandatory_segments(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Scans PDF for Mandatory Segments and Must Use fields.
        Returns a structured list of these elements.
        """
        self.logger.info(f"[856 Flow] Extracting mandatory segments from: {pdf_path}")
        
        try:
            pdf_text = extract_text_from_pdf(pdf_path)
        except Exception as e:
            self.logger.error(f"Failed to read PDF: {e}")
            return []

        # Truncate if necessary (context window management)
        # 856 specs can be large, but usually the definition part fits in 100k chars
        if len(pdf_text) > 120000:
            self.logger.warning("PDF text very large, truncating to 120k chars")
            pdf_text = pdf_text[:120000]

        prompt = self._build_extraction_prompt(pdf_text)
        
        try:
            response = self.ai_client.get_completion(
                prompt,
                system_prompt="You are a Senior EDI Implementation Specialist. Your job is to extract precise constraints from vendor specifications."
            )
            self.logger.info(f"Raw AI Response: {response[:500]}...") # Debug log
            
            data = self._parse_json(response)
            segments = data.get("mandatory_segments", [])
            self.logger.info(f"Extracted {len(segments)} mandatory segments")
            return segments
            
        except Exception as e:
            self.logger.error(f"Error in AI extraction: {e}")
            return []

    def _build_extraction_prompt(self, context: str) -> str:
        return f"""
You are analyzing a Vendor EDI 856 (Advance Ship Notice) Specification PDF.

YOUR OBJECTIVE:
Identify ALL segments that are marked as 'Mandatory' (M) or 'Must Use'.
For each Mandatory segment, identify individual Fields/Elements that are 'Must Use' (M) or 'Required' (R).

Ignoring Optional segments (O) for now, unless they are critical conditional segments (like Item details inside a mandatory loop).
Focus heavily on gathering "Must Use" fields.

DOC TEXT:
{context}

RESPONSE FORMAT (Strict JSON):
{{
  "mandatory_segments": [
    {{
      "segment": "SegmentID (e.g. BSN)",
      "description": "Description of segment",
      "fields": [
         {{
            "id": "FieldID (e.g. BSN01)",
            "req": "Must Use", 
            "description": "Field Description",
            "values": ["List", "Of", "Hardcoded", "Values", "If", "Mentioned"] 
         }},
         {{
            "id": "BSN02",
            "req": "Must Use",
            "description": "Shipment ID",
            "values": [] 
         }}
      ]
    }}
  ]
}}

INSTRUCTIONS:
1. "values": If the spec says "Use '00' for Original", put ["00"]. If it's a dynamic field like Date, leave empty [].
2. Identify Header, Hierarchy, and Detail segments.
3. Be exhaustive for Mandatory segments.
4. Return ONLY valid JSON.
"""

    def _parse_json(self, response: str) -> Dict[str, Any]:
        """Helper to parse JSON from AI response."""
        try:
            # Clean markdown
            if "```json" in response:
                response = response.split("```json")[-1].split("```")[0].strip()
            elif "```" in response:
                response = response.strip("`")
                
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                response = response[start:end+1]
                
            return json.loads(response)
        except Exception as e:
            self.logger.warning(f"JSON Parsing failed: {e}")
            return {"mandatory_segments": []}
