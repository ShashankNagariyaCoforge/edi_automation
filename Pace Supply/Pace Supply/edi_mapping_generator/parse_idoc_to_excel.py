
import re
import sys
import pandas as pd
import os

# Configuration
INPUT_FILE = "GLBRGTX_ORDERSCPG_d.txt"
OUTPUT_FILE = "GLB_RGTX_ORDERSCPG_COMPLETE.xlsx"

# Regex Patterns
REGEX_START = re.compile(r'^([A-Z0-9/_]+)\s+:\s+(.+)$')

# Field Metadata Patterns
REGEX_STATUS = re.compile(r'Status\s*:\s*([A-Za-z]+)', re.IGNORECASE)
REGEX_DATA_TYPE = re.compile(r'internal data type\s*:\s*([A-Z0-9]+)', re.IGNORECASE)
REGEX_INTERNAL_LENGTH = re.compile(r'Internal length\s*:\s*(\d+)', re.IGNORECASE)
REGEX_POSITION = re.compile(r'Position in segment\s*:\s*(\d+)', re.IGNORECASE)
REGEX_OFFSET = re.compile(r'Offset\s*:\s*(\d+)', re.IGNORECASE)
REGEX_EXTERNAL_LENGTH = re.compile(r'external length\s*:\s*(\d+)', re.IGNORECASE)

def parse_idoc_file(filepath):
    if not os.path.exists(filepath):
        print(f"ERROR: Input file not found: {filepath}")
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    rows = []
    
    # State variables
    current_segment_name = None
    current_segment_desc = None
    # We maintain a map of Status found in the Overview section
    segment_status_map = {} 

    block_header = None # (name, desc)
    block_lines = []
    
    def process_block(header, lines_in_block):
        nonlocal current_segment_name, current_segment_desc
        
        name, desc = header
        full_text = " ".join(lines_in_block)
        
        # 1. Check if it's a Segment from Overview (Has Status)
        m_status = REGEX_STATUS.search(full_text)
        if m_status:
            status = m_status.group(1)
            segment_status_map[name] = status
            # We also update current_segment, though in Overview it keeps changing.
            # It doesn't hurt.
            current_segment_name = name
            current_segment_desc = desc
            return

        # 2. Check if it's a Segment from Details (Has "Segment definition")
        if "Segment definition" in full_text:
            current_segment_name = name
            current_segment_desc = desc
            return

        # 3. Check if it's a Field (Has Data Type)
        m_type = REGEX_DATA_TYPE.search(full_text)
        if m_type:
            if not current_segment_name:
                # Field found before any segment context
                return

            # Lookup status (default Optional if not found in map)
            current_status = segment_status_map.get(current_segment_name, "Optional")

            row = {
                "Segment name": current_segment_name,
                "Segment description": current_segment_desc,
                "Status": current_status,
                "Element name": name,
                "Element description": desc,
                "Data type": m_type.group(1),
                "Internal length": "",
                "Position in segment": "",
                "Offset": "",
                "External length": ""
            }
            
            m_ilen = REGEX_INTERNAL_LENGTH.search(full_text)
            if m_ilen: row["Internal length"] = m_ilen.group(1)
            
            m_pos = REGEX_POSITION.search(full_text)
            if m_pos: row["Position in segment"] = m_pos.group(1)
            
            m_off = REGEX_OFFSET.search(full_text)
            if m_off: row["Offset"] = m_off.group(1)
            
            m_elen = REGEX_EXTERNAL_LENGTH.search(full_text)
            if m_elen: row["External length"] = m_elen.group(1)
            
            rows.append(row)
            return

    for line in lines:
        line = line.strip()
        if not line: 
            continue
            
        m_start = REGEX_START.match(line)
        # Exclude known non-element lines that might match regex
        if m_start:
            if "min. number" in line: m_start = None
            if "Segment definition" in line: m_start = None
            if "Released since" in line: m_start = None
            if line.startswith("Extension /GLB"): m_start = None 
            
        if m_start:
            # New block started
            if block_header:
                process_block(block_header, block_lines)
            
            block_header = (m_start.group(1), m_start.group(2))
            block_lines = []
        else:
            # Continue current block
            if block_header:
                block_lines.append(line)
                
    # Process final block
    if block_header:
        process_block(block_header, block_lines)

    # --- VALIDATION ---
    print("--- VALIDATION REPORT ---")
    df = pd.DataFrame(rows)
    
    total_segments = df["Segment name"].nunique() if not df.empty else 0
    total_elements = len(df)
    
    print(f"Total Segments detected: {total_segments}")
    print(f"Total Elements detected: {total_elements}")
    
    # 3. E1EDK01 count
    e1edk01_count = len(df[df["Segment name"] == "E1EDK01"]) if not df.empty else 0
    print(f"E1EDK01 field count: {e1edk01_count}")
    
    # 4. /GLB/ segments check
    glb_segments_count = 0
    if not df.empty:
         glb_segments_count = df[df["Segment name"].str.contains("/GLB/")]["Segment name"].nunique()
    print(f"Extension Segments (/GLB/) detected: {glb_segments_count}")

    # FAIL CONDITIONS
    failed = False
    
    if total_segments == 0:
        print("FAIL: No segments detected.")
        failed = True
    
    if total_elements == 0:
        print("FAIL: No elements detected.")
        failed = True
        
    if e1edk01_count < 30:
        print(f"FAIL: E1EDK01 has {e1edk01_count} fields (expected > 30).")
        failed = True

    if not failed:
        df.to_excel(OUTPUT_FILE, index=False)
        print(f"\nSUCCESS: Excel generated: {OUTPUT_FILE}")
    else:
        print("\nFAILURE: Excel NOT generated due to validation errors.")
        sys.exit(1)

if __name__ == "__main__":
    parse_idoc_file(INPUT_FILE)
