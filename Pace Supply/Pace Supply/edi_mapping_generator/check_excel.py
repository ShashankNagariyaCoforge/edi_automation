
import sys
import os
import openpyxl

def main():
    print("--- Checking Excel Logic ---")
    fpath = "inbound_X12_to_oracle.xlsx"
    if not os.path.exists(fpath):
        fpath = "input/inbound_X12_to_oracle.xlsx"
    
    if not os.path.exists(fpath):
        print("Excel not found")
        return

    wb = openpyxl.load_workbook(fpath)
    ws = wb.active
    
    # Iterate to find Record 0010 and TP_Translator_Code
    # Col A (0) is Field Name? No, Col A is usually Record ID in some formats?
    # Let's check headers.
    
    # Assuming standard structure:
    # A: RecordType (Rec Identifier) OR Record #
    # B: Source
    # C: Value
    # ...
    # J: Logic
    
    # Actually, `read_erp_structure` implies:
    # It finds "Record 0010" in some column?
    
    # Let's just scan for "TP Translator Code" in Column D or E?
    # field_name is usually Col E?
    
    # Actually, let's look at `src/excel_reader.py` to know which column is Field Name.
    # But usually it's easier to just scan row by row.
    
    for row in ws.iter_rows(values_only=True):
        # Look for row containing "Header Identifier" and "0010"
        row_str = [str(x) for x in row]
        if ("Header Identifier" in str(row) or "Location Identifier" in str(row)) and "0010" in row_str:
            print(f"Found Row: {row_str}")
            # Col J is index 9
            if len(row) > 9:
                print(f"Logic (Col J): '{row[9]}'")
            else:
                print("Row too short for Col J")

if __name__ == "__main__":
    main()
