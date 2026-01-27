import sys
from pathlib import Path
import json

# Add current directory to path to import src
sys.path.append(str(Path.cwd()))

from src.excel_reader import read_erp_structure
from src.record_processor import RecordProcessor

def debug_mapping_mismatch(record_num="0020"):
    print(f"--- Debugging Record {record_num} ---")
    
    # 1. Read Excel Structure
    excel_path = "input/inbound_X12_to_oracle.xlsx"
    print(f"Reading Excel: {excel_path}")
    try:
        structure = read_erp_structure(excel_path)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return

    excel_fields = structure.get(record_num, [])
    if not excel_fields:
        print(f"No fields found in Excel for record {record_num}")
        print(f"Available records: {list(structure.keys())}")
        return

    print(f"Found {len(excel_fields)} fields in Excel for record {record_num}")

    # 2. Load JSON Definition
    json_path = Path(f"src/ERP_json/{record_num}.json")
    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        record_def = json.load(f)
    
    json_fields = record_def.get("fields", {})
    print(f"Found {len(json_fields)} fields in JSON for record {record_num}")
    
    # 3. Compare
    # Instantiate processor just to access normalization logic if we want, or copy it
    # We can mock ai_client as None
    processor = RecordProcessor(None, {}, {}) 
    
    matches = 0
    mismatches = 0
    
    print("\n--- Field Analysis ---")
    print(f"{'Excel Field Name':<50} | {'Normalized':<40} | {'Status'}")
    print("-" * 110)
    
    for item in excel_fields:
        excel_name = item["field_name"]
        norm_name = processor._normalize_field_name(excel_name)
        
        # Check direct match
        found = False
        match_type = ""
        
        if excel_name in json_fields:
            found = True
            match_type = "Exact Match"
        elif norm_name in json_fields:
            found = True
            match_type = "Normalized Match"
        
        status = f"OK ({match_type})" if found else "MISSING"
        if found:
            matches += 1
        else:
            mismatches += 1
            
        print(f"{excel_name:<50} | {norm_name:<40} | {status}")

    print("\n--- Summary ---")
    print(f"Total Excel Fields: {len(excel_fields)}")
    print(f"Matches: {matches}")
    print(f"Mismatches: {mismatches}")

if __name__ == "__main__":
    debug_mapping_mismatch("0020")
