from excel_reader import read_erp_structure
import json

STRUCTURE_FILE = "../inbound_X12_to_oracle.xlsx"

try:
    print(f"Reading structure from {STRUCTURE_FILE}...")
    structure = read_erp_structure(STRUCTURE_FILE)
    print(f"Found {len(structure)} record types: {list(structure.keys())}")
    
    if "0010" in structure:
        print("\n--- Record 0010 Fields ---")
        fields = structure["0010"]
        print(f"Count: {len(fields)}")
        for f in fields:
            print(f" - {f['field_name']} (Ref: {f['record_ref']}, Row: {f['row_idx']})")
    else:
        print("\nERROR: 0010 NOT FOUND IN STRUCTURE!")

    if "Rec" in structure:
        print("\n--- Record Rec (Suspicious) ---")
        fields = structure["Rec"]
        for f in fields:
             print(f" - {f['field_name']} (Ref: {f['record_ref']}, Row: {f['row_idx']})")

except Exception as e:
    print(f"Error: {e}")
