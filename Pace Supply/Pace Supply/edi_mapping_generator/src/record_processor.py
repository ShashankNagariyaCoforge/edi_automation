"""
Record processor module - processes a single record type.
"""
import json
import traceback
from pathlib import Path
from typing import Dict, List, Any
from ai_client import AIClient
from logger import get_logger
from standard_mappings import apply_standard_mappings


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
            Dictionary with field mappings matching the Excel columns (B, C, D, E).
        """
        field_names = [f["field_name"] for f in fields]
        self.logger.info(f"Processing record {record_num} with {len(field_names)} fields (Phase 3)")
        
        # 1. Load Canonical JSON
        record_def = self._load_record_json(record_num)
        if not record_def:
            self.logger.warning(f"No Canonical JSON found for record {record_num}")
            return {}

        # 2. Normalize and Deduplicate Fields for Prompt
        # Map normalized_name -> list of original_field_dicts
        norm_map = {}
        for f in fields:
            norm = self._normalize_field_name(f["field_name"])
            if norm not in norm_map:
                norm_map[norm] = []
            norm_map[norm].append(f)
            
        unique_targets = list(norm_map.keys())
        
        # Create a simplified list of fields for the PROMPT using normalized names
        # We pick the first occurrence's logic description, or merge them?
        # Let's pick the one that has length > 0, if any.
        prompt_fields = []
        for norm in unique_targets:
            # Find best logic desc
            best_logic = ""
            for orig in norm_map[norm]:
                l = orig.get("logic_desc", "")
                if l and hasattr(l, 'strip'):
                     l = l.strip()
                if l and len(l) > len(best_logic):
                    best_logic = l
            
            # DEBUG: Log logic decision for critical fields
            if record_num == "0010":
                self.logger.info(f"Field Debug [0010]: {norm} -> Logic: '{best_logic}'")
            elif "Header_Identifier" in norm or "TP_Translator" in norm:
                self.logger.info(f"Field Debug: {norm} -> Logic: '{best_logic}'")

            prompt_fields.append({
                "field_name": norm,
                "logic_desc": best_logic
            })

        try:
            # Pass unique normalized fields to prompt
            prompt = self._build_phase3_prompt(record_num, prompt_fields, record_def)
            
            response = self.ai_client.get_completion(
                prompt,
                system_prompt="You are an EDI Mapping Engine. Output strict JSON only. Do not invent fields."
            )
            
            # Parse response expecting normalized keys
            unique_mappings = self.ai_client._parse_response(response, unique_targets)
            
            # 3. Fan-out results to original field names
            final_mappings = {}
            for original_field in fields:
                name = original_field["field_name"]
                norm = self._normalize_field_name(name)
                if norm in unique_mappings:
                    final_mappings[name] = unique_mappings[norm]
                else:
                    final_mappings[name] = {} # Should not happen if _parse_response fills defaults
            
            return final_mappings
            
        except Exception as e:
            self.logger.error(f"LLM failure for record {record_num}: {e}\\n{traceback.format_exc()}")
            return {}

    def _build_phase3_prompt(self, record_num: str, fields: List[Dict[str, Any]], record_def: Dict[str, Any]) -> str:

        """Construct the prompt for Phase 3 including full JSON definition for semantic matching."""
        
        # Prepare Knowledge Base (JSON)
        # We dump the entire JSON content so the LLM can see all keys and structure
        knowledge_base_str = json.dumps(record_def, indent=2)

        # Prepare Constraints (PDF) - Filtered
        filtered_constraints = self._filter_constraints_for_record(record_def)
        constraints_str = json.dumps(filtered_constraints, indent=2)

        # Prepare Sample Data (EDI) - Simplified
        sample_str = "No Sample EDI File Provided."
        if self.edi_parsed:
            sample_str = ""
            for seg, occs in self.edi_parsed.items():
                sample_str += f"{seg}: {len(occs)} occurrences. Example: {occs[0] if occs else 'empty'}\\n"

        prompt_parts = [
            "You are an expert EDI Integration Architect.",
            "We are working on an automation to prepare an X12_to_Oracle mapping file.",
            "Your task is to prepare this mapping for a specific Record Group.",
            "",
            f"### CONTEXT: Record {record_num}",
            f"Target Fields to Map: {json.dumps([f['field_name'] for f in fields])}",
        ]

        # Prepare Logic Map - Filter out empty strings to avoid ambiguity
        logic_map = {}
        for f in fields:
            l = f.get('logic_desc', '')
            if l and str(l).strip():
                logic_map[f['field_name']] = str(l).strip()
        
        # DEBUG: Log logic map
        if record_num == "0010":
            self.logger.info(f"Prompt Logic Map [0010]: {json.dumps(logic_map)}")

        prompt_parts.append(f"Logic Descriptions (Column J): {json.dumps(logic_map)}")
        prompt_parts.append("")
        
        prompt_parts.extend([
            "### STEP 1: CONSULT KNOWLEDGE BASE (Source of Truth)",
            "The following JSON defines the available fields and their rules.",
            "CRITICAL: The 'Target Fields' above might use slightly different naming or casing than the keys in this JSON.",
            "You must SEARCH this JSON for the matching definition. Keys might be nested.",
            "- If a field matches 'record_number', use the root 'record_number' or related constant.",
            "- If a field matches a key inside 'record_classification', use that.",
            "- Use 'semantic similarity' to resolve Excel field names to JSON keys.",
            "",
            "#### KNOWLEDGE BASE JSON:",
            knowledge_base_str,
            "",
            "### STEP 2: CONSULT EXTRA RULES (From PDF)",
            "These are specific validation rules extracted from the Vendor Specification.",
            constraints_str,
            "",
            "### STEP 3: CHECK EDI DATA (Sample File)",
            "Confirm availability of segments in the actual file:",
            sample_str,
            "",
            "### STEP 4: GENERATE OUTPUT",
            "Based on the above, generate the mapping JSON for the requested Target Fields.",
            "Return a JSON object where keys are the specific Field Names from the 'Target Fields' list.",
            'Values must be an object with keys: "B", "C".',
            "",
            "## COLUMN DEFINITIONS (CRITICAL)",
            "",
            "**Column B (SOURCE)**: Where to fetch the value FROM the EDI X12 file.",
            "  - Format: SegmentElement (e.g., 'BEG03' means element 03 of BEG segment)",
            "  - Examples: 'GS02', 'BEG03', 'REF02', 'N102', 'PO101'",
            "  - If the field is NOT from EDI (constant/fixed), leave B EMPTY.",
            "  - If logic depends on CONDITIONAL fields (see STEP 5), list ALL referenced segments here (e.g., 'N1, N2, N3').",
            "",
            "**Column C (VALUE)**: The FIXED/CONSTANT value if not derived from EDI.",
            "  - Use this ONLY when 'value_source' is 'constant', 'fixed_by_layout', 'oracle_standard', 'erp_constant' etc.",
            "  - Put the actual value here (e.g., '0010', 'CT', 'CTL', 'X12', '850').",
            "  - If the field IS from EDI (Column B populated), leave C EMPTY.",
            "",
            "**Validation Warning (validation_warning)**:",
            "  - Analyze the provided Logic Description vs Vendor Constraints.",
            "  - If the logic depends on specific values (e.g., 'BEG02 = DS'), check if the Vendor Spec allows OTHER values (e.g., 'BG', 'SA').",
            "  - If the logic does NOT cover all allowed values from the Vendor Spec, output a warning string here.",
            "  - Example: 'Vendor Spec allows BEG02 values [DS, BG, SA] but logic only covers [DS].'",
            "  - If ok, leave null or empty string.",
            "",
            "### STEP 5: HANDLE SPECIFIC LOGIC (Column J)",
            "For each target field in request, I have provided 'Logic Description' if available.",
            "1. IF LOGIC DESCRIPTION IS EMPTY or whitespace, IGNORE IT. Use the default mapping from the Knowledge Base (x12_mapping).",
            "2. If Logic Description says 'Constant X', put X in Column C, clear B.",
            "3. If Logic Description has conditions (e.g., 'If BEG02=DS...'):",
            "   - Extract all segments mentioned in the RESULT of the condition (e.g. 'take from N104' -> B='N104').",
            "   - If multiple conditions lead to different segments, list them all in B (e.g. 'N1, N2, N3').",
            "   - Perform the Validation Check described above.",
            "",
            "## JSON SCHEMA",
            "{",
            '  "Field_Name": {',
            '      "B": "EDI Source (e.g., BEG03) or empty",',
            '      "C": "Fixed Value or empty",',
            '      "validation_warning": "Warning message or null"',
            "  }",
            "}",
            "",
            "IMPORTANT: Do NOT invent mappings. Only use what the Knowledge Base provides.",
            "Strict JSON only."
        ])
        

        
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
        if self.edi_parsed:
            if found_in_sample:
                logic.append(f"Sample: '{sample_val}'")
            else:
                logic.append("Not found in sample")
        else:
             # checking specifically if we have parsed data at all
             pass # Don't add text if no sample provided
            
        if constraint_info:
            logic.append(constraint_info)
            
        return {
            "segment": f"{segment}-{element_idx_str.zfill(2)}",
            "constant": None,
            "logic": "; ".join(logic)
        }

