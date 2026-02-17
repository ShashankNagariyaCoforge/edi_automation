"""
Gap Analyzer Module — Nestle Flow (Redesigned).

Produces a 16-column output grid anchored on every SAP IDoc ERP field.
For each field:
  1. Reverse-lookup standard mapping  → X12 segment/element
  2. Cross-reference with PDF spec    → confirm, flag discrepancies
  3. AI semantic match (unmapped)      → suggest best PDF element
"""
from typing import List, Dict, Any, Tuple, Optional
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from logger import get_logger


class GapAnalyzer:
    """
    ERP-centric gap analysis engine.

    Inputs:
      - erp_fields:          list of SAP IDoc field dicts  (from ErpLoader)
      - standard_loader:     StandardLoader instance (with reverse lookup)
      - pdf_segments:        list of segment dicts from full PDF extraction
      - ai_client:           AIClient for semantic matching
    """

    # Grid column order (header row)
    GRID_HEADERS = [
        "SAP Segment",        # 0
        "SAP Segment Desc",   # 1
        "SAP Field",          # 2
        "SAP Field Desc",     # 3
        "SAP Data Type",      # 4
        "SAP Length",          # 5
        "X12 Segment",        # 6
        "X12 Element",        # 7
        "X12 Element Desc",   # 8
        "Mapping Rule",       # 9
        "PDF Seg Status",     # 10
        "PDF Elem Status",    # 11
        "PDF Values",         # 12
        "Mapping Source",     # 13
        "Confidence",         # 14
        "Notes",              # 15
    ]

    def __init__(self, standard_loader, pdf_segments: List[Dict], ai_client=None):
        self.standard_loader = standard_loader
        self.ai_client = ai_client
        self.logger = get_logger()

        # Build a flat PDF lookup: (Segment, ElementID) → element info
        self.pdf_lookup: Dict[Tuple[str, str], Dict] = {}
        # Also keep segment-level info: segment_code → segment dict
        self.pdf_seg_lookup: Dict[str, Dict] = {}

        self._build_pdf_index(pdf_segments)

    # ------------------------------------------------------------------ #
    #  PDF Index                                                          #
    # ------------------------------------------------------------------ #

    def _build_pdf_index(self, pdf_segments: List[Dict]):
        """Build fast lookup tables from the PDF extraction output."""
        for seg in pdf_segments:
            seg_code = seg.get("segment", "").strip().upper()
            if not seg_code:
                continue

            self.pdf_seg_lookup[seg_code] = {
                "description": seg.get("description", ""),
                "status": seg.get("status", ""),
            }

            for field in seg.get("fields", []):
                elem_id = str(field.get("id", "")).strip().upper()
                if not elem_id:
                    continue
                # Normalize: if id is just "01", prepend segment code
                if len(elem_id) <= 2 and seg_code not in elem_id:
                    elem_id = f"{seg_code}{elem_id}"

                self.pdf_lookup[(seg_code, elem_id)] = {
                    "description": field.get("description", ""),
                    "status": field.get("status", ""),
                    "values": field.get("values", []),
                }

        self.logger.info(
            f"PDF Index: {len(self.pdf_seg_lookup)} segments, "
            f"{len(self.pdf_lookup)} elements"
        )

    # ------------------------------------------------------------------ #
    #  Main Analysis                                                      #
    # ------------------------------------------------------------------ #

    def analyze(self, erp_fields: List[Dict[str, Any]]) -> Tuple[List[List[str]], Dict]:
        """
        Produces the full output grid and flags dict.
        Returns: (grid, flags)
          - grid: list of rows (each row is a list of strings). Row 0 = headers.
          - flags: { row_idx: { "col": int, "reason": str } }  for flagged cells
        """
        grid: List[List[str]] = [list(self.GRID_HEADERS)]
        flags: Dict[int, Dict[str, Any]] = {}  # row_idx → {"col": 9, "reason": "..."}

        # Collect unmapped fields for batch AI matching
        unmapped_fields: List[Dict] = []
        unmapped_indices: List[int] = []  # grid row indices (1-based)
        # Track STANDARD+PDF rows with PDF values for value flagging
        flaggable_rows: List[Dict] = []  # {"row_idx", "mapping_rule", "pdf_values", "x12_elem"}

        for erp in erp_fields:
            sap_seg = erp["sap_segment"]
            sap_field = erp["sap_field"]

            # --- Step 1: Standard reverse lookup ---
            std_mappings = self.standard_loader.get_by_sap_field(sap_seg, sap_field)

            if std_mappings:
                # Use first (best) standard mapping
                std = std_mappings[0]
                x12_seg = std["x12_segment"]
                x12_elem = std["x12_element"]
                x12_desc = std["description"]
                mapping_rule = std["mapping_rule"]
                std_notes = std.get("notes", "")  # Notes from standard Excel

                # --- Step 2: PDF cross-reference ---
                pdf_elem = self.pdf_lookup.get((x12_seg, x12_elem))
                pdf_seg_info = self.pdf_seg_lookup.get(x12_seg, {})

                if pdf_elem:
                    # STANDARD + PDF confirmed
                    source = "STANDARD+PDF"
                    confidence = "HIGH"
                    pdf_seg_status = pdf_seg_info.get("status", "")
                    pdf_elem_status = pdf_elem.get("status", "")
                    pdf_values = self._format_values(pdf_elem.get("values", []))
                    notes = std_notes  # Use notes from standard mapping Excel
                    x12_desc_display = pdf_elem.get("description") or x12_desc
                else:
                    # Standard mapping only, not in PDF
                    source = "STANDARD"
                    confidence = "MEDIUM"
                    pdf_seg_status = ""
                    pdf_elem_status = ""
                    pdf_values = ""
                    notes = std_notes  # Use notes from standard mapping Excel
                    x12_desc_display = x12_desc

                row = [
                    sap_seg,
                    erp["sap_segment_desc"],
                    sap_field,
                    erp["sap_field_desc"],
                    erp["sap_data_type"],
                    erp["sap_external_length"],
                    x12_seg,
                    x12_elem,
                    x12_desc_display,
                    mapping_rule,
                    pdf_seg_status,
                    pdf_elem_status,
                    pdf_values,
                    source,
                    confidence,
                    notes,
                ]
                grid.append(row)

                # Track for value flagging (only STANDARD+PDF with values)
                if source == "STANDARD+PDF" and pdf_values:
                    flaggable_rows.append({
                        "row_idx": len(grid) - 1,
                        "mapping_rule": mapping_rule,
                        "pdf_values": pdf_values,
                        "x12_elem": x12_elem,
                    })

            else:
                # No standard mapping — placeholder row; will AI-match later
                row = [
                    sap_seg,
                    erp["sap_segment_desc"],
                    sap_field,
                    erp["sap_field_desc"],
                    erp["sap_data_type"],
                    erp["sap_external_length"],
                    "",  # x12_seg
                    "",  # x12_elem
                    "",  # x12_desc
                    "",  # mapping_rule
                    "",  # pdf_seg_status
                    "",  # pdf_elem_status
                    "",  # pdf_values
                    "UNMAPPED",
                    "",
                    "",
                ]
                grid.append(row)
                unmapped_fields.append(erp)
                unmapped_indices.append(len(grid) - 1)

        # --- Step 3: AI Semantic Matching for unmapped fields ---
        if unmapped_fields and self.ai_client and self.pdf_lookup:
            self.logger.info(f"Running AI semantic matching for {len(unmapped_fields)} unmapped fields...")
            ai_matches = self._batch_ai_match(unmapped_fields)

            for idx, match in zip(unmapped_indices, ai_matches):
                if match and match.get("x12_element"):
                    grid[idx][6] = match.get("x12_segment", "")
                    grid[idx][7] = match.get("x12_element", "")
                    grid[idx][8] = match.get("x12_description", "")
                    grid[idx][9] = match.get("mapping_rule", "Semantic match")
                    # PDF info for the matched element
                    pdf_key = (match.get("x12_segment", ""), match.get("x12_element", ""))
                    pdf_elem = self.pdf_lookup.get(pdf_key, {})
                    pdf_seg_info = self.pdf_seg_lookup.get(match.get("x12_segment", ""), {})
                    grid[idx][10] = pdf_seg_info.get("status", "")
                    grid[idx][11] = pdf_elem.get("status", "")
                    grid[idx][12] = self._format_values(pdf_elem.get("values", []))
                    grid[idx][13] = "AI_MATCH"
                    grid[idx][14] = match.get("confidence", "LOW")
                    grid[idx][15] = match.get("reason", "")

        # --- Step 4: AI Value Flagging for STANDARD+PDF rows ---
        if flaggable_rows and self.ai_client:
            self.logger.info(f"Running AI value flagging for {len(flaggable_rows)} standard+PDF rows...")
            flag_results = self._flag_value_discrepancies(flaggable_rows)
            for row_idx, reason in flag_results.items():
                flags[row_idx] = {"col": 9, "reason": reason}
            self.logger.info(f"Flagged {len(flags)} rows with value discrepancies")

        # Summary
        total = len(grid) - 1
        sources = {}
        for row in grid[1:]:
            s = row[13]
            sources[s] = sources.get(s, 0) + 1
        self.logger.info(f"Grid built: {total} rows. Sources: {sources}")

        return grid, flags

    # ------------------------------------------------------------------ #
    #  AI Semantic Matching                                               #
    # ------------------------------------------------------------------ #

    def _batch_ai_match(self, unmapped_fields: List[Dict]) -> List[Optional[Dict]]:
        """
        Use LLM to find the best PDF element match for each unmapped SAP field.
        Processes in parallel batches to avoid token limits.
        """
        BATCH_SIZE = 30

        # Prepare compact PDF catalogue
        pdf_catalogue = []
        for (seg, elem), info in self.pdf_lookup.items():
            pdf_catalogue.append({
                "seg": seg,
                "elem": elem,
                "desc": info.get("description", ""),
            })

        pdf_catalogue_str = json.dumps(pdf_catalogue, indent=None)

        # Split into batches
        batches = []
        for i in range(0, len(unmapped_fields), BATCH_SIZE):
            batches.append(unmapped_fields[i : i + BATCH_SIZE])

        self.logger.info(f"AI matching: {len(unmapped_fields)} fields in {len(batches)} parallel batches")

        def _process_batch(batch):
            batch_input = []
            for f in batch:
                batch_input.append({
                    "sap_segment": f["sap_segment"],
                    "sap_field": f["sap_field"],
                    "sap_desc": f["sap_field_desc"],
                })

            prompt = f"""
You are an EDI/SAP Integration Expert.

I have SAP IDoc fields that need to be mapped to X12 850 EDI elements.
Below is the full list of available X12 elements from the vendor's PDF spec,
followed by the SAP fields that need matches.

## Available X12 Elements (from Vendor PDF):
{pdf_catalogue_str}

## SAP Fields to Match:
{json.dumps(batch_input, indent=2)}

## TASK:
For each SAP field, find the BEST matching X12 element from the catalogue above.
Match based on semantic similarity of descriptions, field names, and domain knowledge.

## OUTPUT FORMAT — Strict JSON array:
[
  {{
    "sap_field": "<field_name>",
    "sap_segment": "<sap_segment>",
    "x12_segment": "<matched X12 segment or empty>",
    "x12_element": "<matched X12 element or empty>",
    "x12_description": "<description of matched element>",
    "mapping_rule": "<brief mapping logic>",
    "confidence": "HIGH" | "MEDIUM" | "LOW" | "NONE",
    "reason": "<1-line explanation>"
  }}
]

## RULES:
1. If no reasonable match exists, set x12_element to "" and confidence to "NONE".
2. Do NOT force matches. Only match when semantically meaningful.
3. Consider SAP segment context (E1EDK01 = header, E1EDP01 = item, E1EDKA1 = partner, etc.)
4. Return ONLY valid JSON, no markdown.
"""
            try:
                response = self.ai_client.get_completion(
                    prompt,
                    system_prompt="You are an EDI/SAP mapping specialist. Return ONLY valid JSON."
                )
                return self._parse_ai_matches(response, batch)
            except Exception as e:
                self.logger.error(f"AI matching batch failed: {e}")
                return [None] * len(batch)

        # --- Run batches in parallel ---
        all_matches = [None] * len(unmapped_fields)
        with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
            futures = {}
            for batch_idx, batch in enumerate(batches):
                future = executor.submit(_process_batch, batch)
                futures[future] = batch_idx

            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    results = future.result()
                    start = batch_idx * BATCH_SIZE
                    for j, match in enumerate(results):
                        all_matches[start + j] = match
                except Exception as e:
                    self.logger.error(f"Batch {batch_idx} future failed: {e}")

        return all_matches

    def _parse_ai_matches(self, response: str, batch: List[Dict]) -> List[Optional[Dict]]:
        """Parse AI response into a list of match dicts, aligned with batch order."""
        try:
            cleaned = response
            if "```" in cleaned:
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
                else:
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()

            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1:
                cleaned = cleaned[start : end + 1]

            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                return [None] * len(batch)

            # Index by (sap_segment, sap_field)
            match_map = {}
            for item in parsed:
                key = (item.get("sap_segment", ""), item.get("sap_field", ""))
                match_map[key] = item

            results = []
            for f in batch:
                key = (f["sap_segment"], f["sap_field"])
                results.append(match_map.get(key))
            return results

        except Exception as e:
            self.logger.warning(f"Failed to parse AI match response: {e}")
            return [None] * len(batch)

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_values(values) -> str:
        if not values:
            return ""
        if isinstance(values, list):
            return ", ".join(str(v) for v in values)
        return str(values)

    @staticmethod
    def _check_discrepancies(std_desc: str, pdf_desc: str) -> str:
        """Flag if standard and PDF descriptions differ significantly."""
        if not std_desc or not pdf_desc:
            return ""
        std_lower = std_desc.lower().strip()
        pdf_lower = pdf_desc.lower().strip()
        if std_lower == pdf_lower:
            return ""
        # Simple word overlap check
        std_words = set(std_lower.split())
        pdf_words = set(pdf_lower.split())
        overlap = std_words & pdf_words
        if len(overlap) < min(len(std_words), len(pdf_words)) * 0.3:
            return f"⚠ Description mismatch: Std='{std_desc}' vs PDF='{pdf_desc}'"
        return ""

    # ------------------------------------------------------------------ #
    #  AI Value Flagging                                                   #
    # ------------------------------------------------------------------ #

    def _flag_value_discrepancies(self, flaggable_rows: List[Dict]) -> Dict[int, str]:
        """
        Uses AI to compare mapping_rule vs PDF values for each flaggable row.
        Returns { row_idx: reason_string } for rows with discrepancies.
        """
        if not flaggable_rows:
            return {}

        # Build input for AI
        items = []
        for fr in flaggable_rows:
            items.append({
                "row_idx": fr["row_idx"],
                "x12_element": fr["x12_elem"],
                "mapping_rule": fr["mapping_rule"],
                "pdf_values": fr["pdf_values"],
            })

        prompt = f"""
You are an EDI mapping validator.

Below is a list of X12 elements where we have a standard mapping rule AND the vendor PDF specifies allowed values.
Your task: For each item, check if ALL the PDF values are covered by the mapping rule.

## Items to check:
{json.dumps(items, indent=2)}

## TASK:
For each item, compare the "pdf_values" against the "mapping_rule".
- If the mapping rule mentions/handles ALL the PDF values → the item is CLEAN (no flag needed).
- If the PDF has values that are NOT mentioned or handled in the mapping rule → FLAG it.

## OUTPUT — Strict JSON array:
[
  {{
    "row_idx": <number>,
    "flagged": true/false,
    "uncovered_values": ["AB", "CD"],
    "reason": "PDF specifies values AB, CD for <element> but the mapping rule only covers TE and FX. Rules for AB, CD need to be defined."
  }}
]

## RULES:
1. Only flag items where there is a genuine gap — PDF values not handled by the rule.
2. The reason must be a single clear line explaining what's missing.
3. Return ONLY valid JSON, no markdown.
"""
        try:
            response = self.ai_client.get_completion(
                prompt,
                system_prompt="You are an EDI mapping validation expert. Return ONLY valid JSON."
            )

            # Parse response
            cleaned = response.strip()
            if "```" in cleaned:
                import re
                match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', cleaned)
                if match:
                    cleaned = match.group(1).strip()

            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end + 1]

            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                return {}

            results = {}
            for item in parsed:
                if item.get("flagged") and item.get("reason"):
                    results[item["row_idx"]] = item["reason"]

            return results

        except Exception as e:
            self.logger.error(f"AI value flagging failed: {e}")
            return {}

