from typing import List, Dict, Any, Tuple
from logger import get_logger

class GapAnalyzer:
    """
    Compares the Vendor PDF Requirements against the Standard Mapping.
    Identifies:
    1. Matches (In both)
    2. PDF Only (New requirement?)
    3. Standard Only (Missing in PDF?)
    """
    def __init__(self, standard_mappings: Dict[tuple, Dict[str, Any]]):
        self.standard = standard_mappings # Key: (Seg, Elem)
        self.logger = get_logger()

    def analyze(self, pdf_constraints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Input: List of dicts from PDF extractor.
               Each dict should look like:
               { "segment": "BEG", "fields": [ {"id": "BEG01", "description": "..."} ] }
               
        Output: A flattened list of rows for the UI Grid.
        Row Structure: similar to 850/856 grid but with "Status" column.
        """
        
        results = []
        
        # 1. Process PDF items
        pdf_keys = set()
        
        self.logger.info(f"GapAnalyzer Input Type: {type(pdf_constraints)}")
        self.logger.info(f"GapAnalyzer Input Content (First 500 chars): {str(pdf_constraints)[:500]}")

        # Handle Dict input ({"segments": {...}}) or List input
        segments_list = []
        if isinstance(pdf_constraints, dict):
            # Transform dict format to list format for processing
            # Dict format: {"segments": {"BEG": {"req": "M", "elements": {...}}}}
            segs = pdf_constraints.get("segments", {})
            for seg_name, details in segs.items():
                # Flatten for processing
                fields = []
                # Elements are in details["elements"] -> {"01": ..., "02": ...}
                elements = details.get("elements", {})
                for elem_idx, elem_info in elements.items():
                    fields.append({
                        "id": elem_idx,
                        "description": f"Element {elem_idx}",
                        "values": elem_info.get("values", [])
                    })
                
                segments_list.append({
                    "segment": seg_name,
                    "fields": fields
                })
        elif isinstance(pdf_constraints, list):
             segments_list = pdf_constraints

        for seg in segments_list:
            seg_code = seg.get("segment")
            seg_desc = seg.get("description", "") # New field
            if not seg_code: continue
            
            for field in seg.get("fields", []):
                elem_code = field.get("id") # e.g. "BEG01" or "01" depending on extractor
                # Normalize PDF extraction to ensure we have "BEG02", "N101" etc
                # If extractor returns just "02", prepend segment? 
                # usually extractor 856 return full ID. let's assume full ID.
                # Just in case:
                if len(elem_code) < 3 and seg_code not in elem_code:
                     elem_code = f"{seg_code}{elem_code}"
                
                key = (seg_code, elem_code)
                pdf_keys.add(key)
                
                # Check Match
                match = self.standard.get(key)
                
                if match:
                    status = "MATCH"
                    sap_segment = match['sap_segment']
                    sap_field = match['sap_field']
                    notes = match['notes']
                else:
                    status = "PDF_ONLY"
                    sap_segment = "?"
                    sap_field = "?"
                    notes = "Found in Vendor Spec but not in Standard Mapping."
                
                # Get values from transformed dict (was field.get("values", ""))
                # field is now {"id":..., "description":..., "values":...}
                pdf_example = str(field.get("values", ""))
                
                row = {
                    "status": status,
                    "x12_segment": seg_code,
                    "seg_desc": seg_desc,
                    "x12_element": elem_code,
                    "description": field.get("description", "No description"),
                    "sap_segment": sap_segment,
                    "sap_field": sap_field,
                    "notes": notes,
                    "pdf_example": pdf_example
                }
                results.append(row)
                
        # 2. Process Standard Only items
        for key, info in self.standard.items():
            if key not in pdf_keys:
                # Missing from PDF
                # We should add this to the grid so the user knows they might be missing something
                # Or maybe they don't need it.
                # Simple lookup for Standard Only items (or leave blank)
                # Since we don't have segment desc in standard map, we can try to infer or leave blank.
                # Let's use a small fallback map for common segments.
                fallback_map = {
                    "BEG": "Beginning Segment for Purchase Order",
                    "REF": "Reference Information",
                    "DTM": "Date/Time Reference",
                    "N1": "Name",
                    "N2": "Additional Name Information",
                    "N3": "Address Information",
                    "N4": "Geographic Location",
                    "PO1": "Baseline Item Data",
                    "PID": "Product/Item Description",
                    "SAC": "Service, Promotion, Allowance, or Charge Information",
                    "CTT": "Transaction Totals",
                    "SE": "Transaction Set Trailer",
                    "GE": "Functional Group Trailer",
                    "IEA": "Interchange Control Trailer",
                    "ISA": "Interchange Control Header",
                    "GS": "Functional Group Header",
                    "ST": "Transaction Set Header",
                    "CUR": "Currency",
                    "FOB": "F.O.B. Related Instructions",
                    "ITD": "Terms of Sale/Deferred Terms of Sale",
                    "TD5": "Carrier Details (Routing Sequence/Transit Time)",
                    "MSG": "Message Text",
                    "SCH": "Line Item Schedule",
                    "ACK": "Line Item Acknowledgment"
                } 
                seg_desc = fallback_map.get(info['x12_segment'], "")
                
                row = {
                    "status": "STANDARD_ONLY",
                    "x12_segment": info['x12_segment'],
                    "seg_desc": seg_desc,
                    "x12_element": info['x12_element'],
                    "description": info['description'],
                    "sap_segment": info['sap_segment'],
                    "sap_field": info['sap_field'],
                    "notes": f"Standard mapping exists, but not found in uploaded PDF. {info['notes']}",
                    "pdf_example": ""
                }
                results.append(row)
                
        # Sort results by Segment then Element for readability
        results.sort(key=lambda x: (x['x12_segment'], x['x12_element']))
        
        # Convert to 2D Grid
        grid = []
        # Header
        grid.append([
            "X12 Seg", 
            "Seg Desc", # New Column
            "X12 Elem", 
            "elem_desc", # Renamed description to elem_desc
            "SAP Seg", 
            "SAP Field", 
            "PDF Example", 
            "Notes",
            "Status"
        ])
        
        for r in results:
            grid.append([
                r["x12_segment"],
                r["seg_desc"],
                r["x12_element"],
                r["description"],
                r["sap_segment"],
                r["sap_field"],
                r["pdf_example"],
                r["notes"],
                r["status"]
            ])
            
        return grid
