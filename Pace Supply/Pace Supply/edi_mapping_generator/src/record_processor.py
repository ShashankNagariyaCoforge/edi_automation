"""
Record processor module - processes a single record type.
"""
import json
import traceback
from pathlib import Path
from typing import Dict, List, Any
from .ai_client import AIClient
from .logger import get_logger
from .standard_mappings import apply_standard_mappings


class RecordProcessor:
    """Processes a single record type to generate mappings using Canonical JSONs."""
    
    def __init__(self, ai_client: AIClient, edi_parsed: Dict[str, List[List[str]]], constraints: Dict[str, Any] = None):
        """
        Initialize record processor.
        
        Args:
            ai_client: Initialized AI client (used for fallbacks if needed)
            edi_parsed: Parsed EDI structure { "SEG": [["el1", ...]] }
            constraints: Extracted constraints from PDF
        """
        self.ai_client = ai_client
        self.edi_parsed = edi_parsed
        self.constraints = constraints or {}
        self.logger = get_logger()
        self.erp_json_dir = Path(__file__).parent / "ERP_json"
    
    def process_record(self, record_num: str, fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Phase 3: Process a single record type using LLM to generate final Excel values.
        
        Args:
            record_num: Record number (e.g., "1000")
            fields: List of fields from the Excel structure needing mapping.
        
        Returns:
            Dictionary with field mappings matching the Excel columns (B, C, D, E, J).
        """
        field_names = [f["field_name"] for f in fields]
        self.logger.info(f"Processing record {record_num} with {len(field_names)} fields (Phase 3)")
        
        # 1. Load Canonical JSON
        record_def = self._load_record_json(record_num)
        if not record_def:
            self.logger.warning(f"No Canonical JSON found for record {record_num}")
            return {}

        try:
            prompt = self._build_phase3_prompt(record_num, field_names, record_def)
            
            response = self.ai_client.get_completion(
                prompt,
                system_prompt="You are an EDI Mapping Engine. Output strict JSON only. Do not invent fields."
            )
            
            mappings = self.ai_client._parse_response(response, field_names)
            return mappings
            
        except Exception as e:
            self.logger.error(f"LLM failure for record {record_num}: {e}\n{traceback.format_exc()}")
            return {}

    def _build_phase3_prompt(self, record_num: str, field_names: List[str], record_def: Dict[str, Any]) -> str:
        """Construct the strict prompt for Phase 3."""
        
        # Prepare Field Definitions (Meaning) from Canonical JSON as Q&A
        field_context = []
        for fname in field_names:
            # Try to find definition
            fdef = record_def.get("fields", {}).get(fname)
            if not fdef:
                # cleanup name using normalization
                norm_name = self._normalize_field_name(fname)
                fdef = record_def.get("fields", {}).get(norm_name)
            
            if fdef:
                # Format as Q&A
                qa_block = [
                    f"Field: {fname}",
                    f"1. What is this field? {fdef.get('description', 'Unknown')}",
                    f"2. Why does it exist? {fdef.get('semantic_role', 'Unknown')}",
                    f"3. Where does it come from? {fdef.get('value_source', 'Unknown')}",
                    f"4. Can X12 provide it? {json.dumps(fdef.get('x12_mapping')) if fdef.get('x12_mapping') else 'No'}",
                    f"5. Should I infer or fix it? {fdef.get('value_type', 'Unknown')}",
                    f"6. Is the value fixed? {fdef.get('fixed_value') if fdef.get('fixed_value') is not None else 'No'}"
                ]
                field_context.append("\n".join(qa_block))
            else:
                field_context.append(f"Field: {fname}\n(No Knowledge Base definition found)")

        # Prepare Constraints (PDF) - Filtered
        filtered_constraints = self._filter_constraints_for_record(record_def)
        constraints_str = json.dumps(filtered_constraints, indent=2)

        # Prepare Sample Data (EDI) - Simplified
        sample_str = ""
        for seg, occs in self.edi_parsed.items():
            sample_str += f"{seg}: {len(occs)} occurrences. Example: {occs[0] if occs else 'empty'}\n"

        prompt_parts = [
            "You are an expert EDI Integration Architect.",
            "We are working on an automation to prepare an X12_to_Oracle mapping file.",
            "Currently, this is done manually whenever a new vendor is onboarded.",
            "This mapping file explains where to pull data from the EDI X12 file so downstream systems can ingest it.",
            "Your task is to prepare this mapping for a specific Record Group.",
            "",
            f"### CONTEXT: Record {record_num}",
            "We have fetched the relevant field definitions from our internal Knowledge Base (JSON).",
            "",
            "### STEP 1: UNDERSTAND THE FIELDS (Q&A From Knowledge Base)",
            "\n\n".join(field_context),
            "",
            "### STEP 2: CONSULT EXTRA RULES (From PDF/RAG)",
            "These are specific validation rules extracted from the Vendor Specification.",
            constraints_str,
            "",
            "### STEP 3: CHECK EDI DATA (Sample File)",
            "Confirm availability of segments in the actual file:",
            sample_str,
            "",
            "### STEP 4: GENERATE OUTPUT",
            "Based on the above, generate the mapping JSON for the requested fields.",
            "Return a JSON object where keys are the specific Field Names.",
            'Values must be an object with keys: "B", "C", "J".',
            "",
            "## COLUMN DEFINITIONS (CRITICAL)",
            "",
            "**Column B (SOURCE)**: Where to fetch the value FROM the EDI X12 file.",
            "  - Format: SegmentElement (e.g., 'BEG03' means element 03 of BEG segment)",
            "  - Examples: 'GS02', 'BEG03', 'REF02', 'N102', 'PO101'",
            "  - If the field is NOT from EDI (constant/fixed), leave B EMPTY.",
            "",
            "**Column C (VALUE)**: The FIXED/CONSTANT value if not derived from EDI.",
            "  - Use this ONLY when 'value_source' is 'constant', 'fixed_by_layout', 'oracle_standard', 'erp_constant' etc.",
            "  - Put the actual value here (e.g., '0010', 'CT', 'CTL', 'X12', '850').",
            "  - If the field IS from EDI (Column B populated), leave C EMPTY.",
            "",
            "**Column J (LOGIC)**: Explain your reasoning briefly.",
            "  - Example: 'Mapped from BEG03 per Knowledge Base' or 'Fixed value per oracle_standard'",
            "",
            "## DECISION RULES",
            "1. Check 'Where does it come from?' (value_source) and 'Can X12 provide it?' (x12_mapping)",
            "2. If value_source is 'x12' and x12_mapping exists → B = segment+element (e.g., 'BEG03'), C = empty",
            "3. If value_source is 'constant', 'fixed_by_layout', 'oracle_standard' → B = empty, C = fixed_value",
            "4. If neither applies → B = empty, C = empty, J = 'Cannot determine mapping'",
            "",
            "## JSON SCHEMA",
            "{",
            '  "Field_Name": {',
            '      "B": "EDI Source (e.g., BEG03) or empty",',
            '      "C": "Fixed Value or empty",',
            '      "J": "Reasoning"',
            "  }",
            "}",
            "",
            "IMPORTANT: Do NOT invent mappings. Only use what the Knowledge Base provides.",
            "Strict JSON only."
        ]
        
        prompt = "\n".join(prompt_parts)
        return prompt

    def _normalize_field_name(self, name: str) -> str:
        """Normalize Excel field name to match JSON key."""
        # Example: "Header Identifier (Location Identifier)" -> "Header_Identifier_Location_Identifier"
        if not name:
            return ""
        # 1. Replace " (" with "_" to separate
        n = name.replace(" (", "_").replace("(", "_")
        # 2. Remove ")"
        n = n.replace(")", "")
        # 3. Replace remaining spaces and dashes
        n = n.replace(" ", "_").replace("-", "_")
        # 4. Collapse multiple underscores
        while "__" in n:
            n = n.replace("__", "_")
        return n

    def _filter_constraints_for_record(self, record_def: Dict[str, Any]) -> Dict[str, Any]:
        """Filter global constraints to only those relevant for this record type to reduce prompt size."""
        relevant_segments = set()
        
        # 1. Identify segments used in this record
        fields = record_def.get("fields", {})
        for fdef in fields.values():
            if isinstance(fdef, dict):
                 # Check direct mapping
                 x12_map = fdef.get("x12_mapping")
                 if isinstance(x12_map, dict):
                     seg = x12_map.get("segment")
                     if seg:
                         relevant_segments.add(seg)
        
        # 2. Filter from self.constraints
        # Structure of constraints is likely { "segments": { "BEG": {...}, ... } }
        if not self.constraints:
            return {}
            
        full_segments = self.constraints.get("segments", {})
        
        # Also keep any general info? Just segments for now.
        filtered_segments = {}
        
        for seg in relevant_segments:
            # Also maybe include basic segments like ISA/GS just in case? No, keep it strict.
            if seg in full_segments:
                filtered_segments[seg] = full_segments[seg]
                
        return {
            "segments": filtered_segments, 
            "note": "Filtered to reduce LLM context usage"
        }

    def _load_record_json(self, record_num: str) -> Dict[str, Any]:
        """Load JSON definition for the record."""
        # Try exact match, then padded
        candidates = [record_num, record_num.zfill(4)]
        for c in candidates:
            fpath = self.erp_json_dir / f"{c}.json"
            if fpath.exists():
                try:
                    with open(fpath, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    self.logger.error(f"Error loading {fpath}: {e}")
        return {}

    def _map_x12_field(self, segment: str, element_idx_str: str, field_def: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to map X12 fields checking sample data and constraints."""
        # 1. Parse element index
        try:
            elem_idx = int(element_idx_str)
        except ValueError:
            return {"segment": f"{segment}-{element_idx_str}", "constant": None, "logic": "Invalid element index"}

        # 2. Check Sample Data
        sample_val = ""
        found_in_sample = False
        
        if segment in self.edi_parsed:
            occurrences = self.edi_parsed[segment]
            # Just take the first occurrence for "Sample Value" display
            if occurrences:
                elements = occurrences[0]
                # EDI elements are 1-based in documentation, 0-based in list
                # But lists in our parser are just values.
                # If we parsed "BEG*00*NE", elements is ["00", "NE"].
                # So "01" is index 0.
                list_idx = elem_idx - 1
                if 0 <= list_idx < len(elements):
                    sample_val = elements[list_idx]
                    found_in_sample = True
        
        # 3. Check Constraints
        constraint_info = ""
        seg_rules = self.constraints.get("segments", {}).get(segment, {})
        if seg_rules:
            req = seg_rules.get("req")
            if req in ["M", "Mandatory"]:
                constraint_info += " [Mandatory]"
            
            # Check allowed values
            elem_rules = seg_rules.get("elements", {}).get(element_idx_str, {})
            allowed = elem_rules.get("values")
            if allowed:
                constraint_info += f" [Allowed: {', '.join(allowed)}]"
                # Validation check
                if found_in_sample and sample_val not in allowed and sample_val:
                     constraint_info += f" [WARNING: Sample '{sample_val}' not in allowed list]"

        # Format Logic string
        logic = []
        if found_in_sample:
            logic.append(f"Sample: '{sample_val}'")
        else:
            logic.append("Not found in sample")
            
        if constraint_info:
            logic.append(constraint_info)
            
        return {
            "segment": f"{segment}-{element_idx_str.zfill(2)}",
            "constant": None,
            "logic": "; ".join(logic)
        }

