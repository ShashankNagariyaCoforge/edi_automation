import sys
import os
import json

# Adjust path to include src
sys.path.append(os.path.join(os.getcwd(), 'src'))

from flow_nestle.standard_loader import StandardLoader
from flow_nestle.gap_analyzer import GapAnalyzer

def test_logic():
    print("--- Testing Standard Loader ---")
    # Path to Excel in root
    excel_path = "EDI850_to_ORDERS05_Mapping_Standard.xlsx"
    if not os.path.exists(excel_path):
        print(f"Error: {excel_path} not found.")
        return

    loader = StandardLoader(excel_path)
    mappings = loader.load()
    print(f"Loaded {len(mappings)} mappings.")
    
    if ("BEG", "BEG03") in mappings:
        print(f"Verified BEG03: {mappings[('BEG', 'BEG03')]}")
    else:
        print("Error: BEG03 not found in mappings.")

    print("\n--- Testing Gap Analyzer ---")
    # Mock PDF Constraints (List Format as returned by new extractor)
    pdf_constraints = [
        {
            "segment": "BEG",
            "fields": [
                {"id": "BEG01", "description": "Purpose Code", "values": ["00"]},
                {"id": "BEG03", "description": "PO Number", "values": ["123456"]}, 
                {"id": "XX99", "description": "Custom Field", "values": ["TEST"]}
            ]
        }
    ]
    
    analyzer = GapAnalyzer(mappings)
    grid = analyzer.analyze(pdf_constraints)
    
    print(f"Grid Rows: {len(grid)}")
    
    # Check headers
    headers = grid[0]
    print(f"Headers: {headers}")
    
    # Check Rows
    found_match = False
    found_pdf_only = False
    found_std_only = False
    
    for row in grid[1:]:
        # Headers: ['X12 Seg', 'X12 Elem', 'Description', 'SAP Seg', 'SAP Field', 'PDF Example', 'Notes', 'Status']
        seg = row[0]
        elem = row[1]
        status = row[7]
        
        if status == "MATCH" and seg == "BEG" and elem == "BEG03":
            found_match = True
        if status == "PDF_ONLY" and seg == "BEG" and elem == "XX99":
            found_pdf_only = True
        if status == "STANDARD_ONLY":
            found_std_only = True
            
    print(f"Found MATCH (BEG03): {found_match}")
    print(f"Found PDF_ONLY (XX99): {found_pdf_only}")
    print(f"Found STANDARD_ONLY: {found_std_only}")

if __name__ == "__main__":
    test_logic()
