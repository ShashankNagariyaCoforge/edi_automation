"""
PDF Constraint Extractor Module.
Uses AI to parse Vendor Implementation Guide PDF and extract structural constraints.
Provides both mandatory-only extraction (legacy) and full extraction (new).

Key design: Splits PDF into page-based chunks to avoid massive single-prompt
extractions that fail due to JSON truncation/corruption.
"""
import json
import re
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from ai_client import AIClient
from logger import get_logger
from pdf_extractor import extract_text_from_pdf


class PdfConstraintExtractor:
    """Extracts EDI constraints from PDF specifications."""

    # Pages per chunk — tuned to stay within token limits
    PAGES_PER_CHUNK = 8

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.logger = get_logger()

    # ------------------------------------------------------------------ #
    #  NEW: Full extraction  (all segments, all elements, all statuses)   #
    # ------------------------------------------------------------------ #

    def extract_all_segments(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract ALL segments from the PDF spec — mandatory, optional, conditional.
        Uses chunked extraction to avoid truncated AI responses.
        """
        self.logger.info(f"[FULL] Extracting ALL segments from PDF: {pdf_path}")

        try:
            pdf_text = extract_text_from_pdf(pdf_path)
        except Exception as e:
            self.logger.error(f"Failed to read PDF: {e}")
            return []

        # Split by page markers (if present) or by character chunks
        chunks = self._split_into_chunks(pdf_text)
        self.logger.info(f"[FULL] Split PDF into {len(chunks)} chunks for extraction")

        all_segments: Dict[str, Dict] = {}  # segment_code → merged segment
        total = len(chunks)

        # --- Parallel chunk extraction ---
        def _process_chunk(args):
            idx, chunk = args
            self.logger.info(f"[FULL] Processing chunk {idx+1}/{total} ({len(chunk)} chars)...")
            try:
                segments = self._extract_chunk(chunk, idx + 1, total)
                self.logger.info(f"[FULL] Chunk {idx+1}: extracted {len(segments)} segments")
                return segments
            except Exception as e:
                self.logger.error(f"[FULL] Chunk {idx+1} failed: {e}")
                return []

        with ThreadPoolExecutor(max_workers=min(len(chunks), 5)) as executor:
            chunk_results = list(executor.map(_process_chunk, enumerate(chunks)))

        # Merge all results
        for segments in chunk_results:
            for seg in segments:
                code = seg.get("segment", "").strip().upper()
                if not code:
                    continue

                if code not in all_segments:
                    all_segments[code] = {
                        "segment": code,
                        "description": seg.get("description", ""),
                        "status": seg.get("status", ""),
                        "fields": [],
                    }

                # Merge fields, avoiding duplicates
                existing_ids = {
                    f.get("id", "").upper() for f in all_segments[code]["fields"]
                }
                for field in seg.get("fields", []):
                    fid = field.get("id", "").strip().upper()
                    if fid and fid not in existing_ids:
                        all_segments[code]["fields"].append(field)
                        existing_ids.add(fid)

        result = list(all_segments.values())
        total_fields = sum(len(s.get("fields", [])) for s in result)
        self.logger.info(
            f"[FULL] Final: {len(result)} unique segments, {total_fields} total fields"
        )
        return result

    def _split_into_chunks(self, text: str) -> List[str]:
        """Split PDF text into manageable chunks for AI processing."""
        # pdf_extractor.py uses "--- Page X ---" markers between pages
        pages = re.split(r'--- Page \d+ ---', text)
        pages = [p.strip() for p in pages if p.strip()]

        if len(pages) <= 1:
            # Fallback: split by character count
            CHUNK_SIZE = 8000
            return [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]

        # Group pages into chunks of PAGES_PER_CHUNK
        chunks = []
        for i in range(0, len(pages), self.PAGES_PER_CHUNK):
            chunk = '\n\n'.join(pages[i:i + self.PAGES_PER_CHUNK])
            if chunk.strip():
                chunks.append(chunk)

        self.logger.info(f"Split {len(pages)} pages into {len(chunks)} chunks")
        return chunks if chunks else [text]

    def _extract_chunk(self, chunk_text: str, chunk_num: int, total_chunks: int) -> List[Dict]:
        """Extract segments from a single chunk of PDF text."""
        prompt = f"""
Analyze this section (chunk {chunk_num}/{total_chunks}) of an EDI Implementation Guide.

## TEXT:
{chunk_text}

## TASK:
Extract ALL EDI segments and their elements/fields found in this section.
Include Mandatory (M), Optional (O), and Conditional (C) segments.

## OUTPUT — Strict JSON array:
[
  {{
    "segment": "BEG",
    "description": "Beginning Segment for Purchase Order",
    "status": "M",
    "fields": [
      {{
        "id": "BEG01",
        "description": "Transaction Set Purpose Code",
        "status": "M",
        "values": ["00"]
      }}
    ]
  }}
]

## RULES:
1. Include ALL segments found in this text section.
2. "status": "M" (Mandatory/Must Use), "O" (Optional), "C" (Conditional), "X" (Not Used).
3. "values": specific allowed values if listed, else [] for dynamic fields.
4. If no EDI segments are found in this text, return an empty array: []
5. Return ONLY valid JSON. No markdown fences, no commentary.
"""
        response = self.ai_client.get_completion(
            prompt,
            system_prompt=(
                "You are an EDI specification parser. "
                "Extract segment and element definitions from the text. "
                "Return ONLY a valid JSON array."
            ),
        )
        return self._parse_json_list(response)

    # ------------------------------------------------------------------ #
    #  LEGACY: Mandatory-only extraction                                  #
    # ------------------------------------------------------------------ #

    def extract_constraints(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Legacy method — just delegates to full extraction now."""
        return self.extract_all_segments(pdf_path)

    # ------------------------------------------------------------------ #
    #  JSON Parsing — resilient to common AI response issues              #
    # ------------------------------------------------------------------ #

    def _parse_json_list(self, response: str) -> List[Dict]:
        """Parse an AI response expected to be a JSON array of segments."""
        try:
            cleaned = self._clean_ai_response(response)
            result = json.loads(cleaned)

            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                # Extract from common wrapper keys
                for key in ("segments", "mandatory_segments", "data"):
                    if key in result and isinstance(result[key], list):
                        return result[key]
                return []
            return []

        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON parse error: {e}")
            # Try to salvage partial JSON
            salvaged = self._salvage_partial_json(response)
            if salvaged:
                self.logger.info(f"Salvaged {len(salvaged)} segments from partial JSON")
                return salvaged
            self.logger.debug(f"Raw AI response (first 500 chars): {response[:500]}")
            return []

    def _parse_json(self, response: str) -> Any:
        """Parse JSON from AI response, handling various formats."""
        try:
            cleaned = self._clean_ai_response(response)
            return json.loads(cleaned)
        except Exception as e:
            self.logger.warning(f"JSON Parsing failed: {e}")
            salvaged = self._salvage_partial_json(response)
            if salvaged:
                return {"segments": salvaged}
            self.logger.debug(f"Raw AI response (first 500 chars): {response[:500]}")
            return {"segments": []}

    def _clean_ai_response(self, response: str) -> str:
        """Strip markdown fences and find the JSON structure in the response."""
        cleaned = response.strip()

        # Remove markdown code fences
        if "```" in cleaned:
            # Try ```json ... ``` first
            match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', cleaned)
            if match:
                cleaned = match.group(1).strip()

        # Find outermost JSON structure
        start_arr = cleaned.find("[")
        start_obj = cleaned.find("{")

        if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
            end = cleaned.rfind("]")
            if end > start_arr:
                return cleaned[start_arr:end + 1]
        elif start_obj != -1:
            end = cleaned.rfind("}")
            if end > start_obj:
                return cleaned[start_obj:end + 1]

        return cleaned

    def _salvage_partial_json(self, response: str) -> List[Dict]:
        """
        Try to extract valid segment objects from a truncated/malformed JSON response.
        Uses regex to find individual complete segment objects.
        """
        segments = []
        try:
            cleaned = self._clean_ai_response(response)

            # Strategy 1: Try progressively truncating from the end
            # Find the last complete object in the array
            if cleaned.startswith("["):
                # Try to close the array at various points
                for end_pos in range(len(cleaned) - 1, 100, -1):
                    if cleaned[end_pos] == '}':
                        attempt = cleaned[:end_pos + 1] + "]"
                        try:
                            parsed = json.loads(attempt)
                            if isinstance(parsed, list):
                                return parsed
                        except json.JSONDecodeError:
                            continue

            # Strategy 2: Extract individual segment objects via regex
            # Look for complete {"segment": "...", ...} blocks
            pattern = r'\{[^{}]*"segment"\s*:\s*"[^"]+?"[^{}]*"fields"\s*:\s*\[(?:[^\[\]]*|\[(?:[^\[\]]*|\[[^\[\]]*\])*\])*\][^{}]*\}'
            matches = re.findall(pattern, cleaned, re.DOTALL)
            for match in matches:
                try:
                    obj = json.loads(match)
                    if isinstance(obj, dict) and "segment" in obj:
                        segments.append(obj)
                except json.JSONDecodeError:
                    continue

        except Exception as e:
            self.logger.debug(f"Salvage attempt failed: {e}")

        return segments
