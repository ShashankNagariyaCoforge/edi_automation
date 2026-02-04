
import sys
import os
import json
from pathlib import Path

# Add src to sys.path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from record_processor import RecordProcessor
from edi_parser import parse_edi_file
from ai_client import AIClient

from mapping_service import MappingService

def main():
    print("--- 0010 Mapping Reproduction (REAL LLM CALL) ---")
    
    # 1. Initialize Service to get Client
    try:
        service = MappingService()
        ai_client = service.ai_client
        print(f"AI Client Initialized: {ai_client.model}")
    except Exception as e:
        print(f"Failed to init service: {e}")
        return

    # 2. Mock EDI Content with GS
    edi_content = "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *230101*1200*U*00401*000000001*0*T*~GS*PO*SENDER*RECEIVER*20230101*1200*1000*X*004010~ST*850*1001~BEG*00*NE*PO123**20230101~"
    parsed_edi = parse_edi_file(edi_content)
    
    # 3. Setup Processor
    processor = RecordProcessor(ai_client, parsed_edi)
    
    # 3. Target Field
    fields = [{
        "field_name": "TP_Translator_Code", 
        "logic_desc": ""
    }]
    
    # 4. Target Field
    fields = [{
        "field_name": "Header Identifier (Location Identifier)", 
        "logic_desc": "" # Empty string, not space
    }]
    
    # 5. Manual Simulation of Process Record
    print("\n--- MANUAL SIMULATION ---")
    
    # A. Normalize
    norm_map = {}
    for f in fields:
        norm = processor._normalize_field_name(f["field_name"])
        if norm not in norm_map:
            norm_map[norm] = []
        norm_map[norm].append(f)
    
    unique_targets = list(norm_map.keys())
    print(f"Normalized Keys: {unique_targets}")
    
    # B. Build Prompt Fields
    prompt_fields = []
    for norm in unique_targets:
        best_logic = ""
        for orig in norm_map[norm]:
            l = orig.get("logic_desc", "")
            if l and len(l) > len(best_logic):
                best_logic = l
        prompt_fields.append({"field_name": norm, "logic_desc": best_logic})
        
    # C. Build Prompt
    record_def = processor._load_record_json("0010")
    prompt = processor._build_phase3_prompt("0010", prompt_fields, record_def)
    
    print("\n--- FINAL PROMPT (Target Fields Section) ---")
    idx = prompt.find("Target Fields to Map:")
    print(prompt[idx:idx+200])
    
    # D. Call LLM
    print("\nSending raw request to LLM...")
    response = ai_client.get_completion(prompt)
    print("\n--- RAW LLM RESPONSE ---")
    print(response)
    
    # E. Parse
    result = ai_client._parse_response(response, unique_targets)
    print("\n--- PARSED RESULT ---")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
