
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.ai_client import AIClient
from src.flow_856.pdf_processor import PdfProcessor856
from src.flow_856.mapping_engine import MappingEngine856
import yaml

def test_flow():
    # Load config
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    client = AIClient(
        base_url=config["llm_base_url"],
        api_key=config["llm_api_key"],
        model=config["llm_model"],
        auth_type=config.get("auth_type", "bearer")
    )
    
    # 1. PDF Extract
    pdf_proc = PdfProcessor856(client)
    input_dir = Path("856")
    pdf_path = list(input_dir.glob("*.pdf"))[0]
    
    print(f"Processing PDF: {pdf_path}")
    segments = pdf_proc.extract_mandatory_segments(str(pdf_path))
    print(f"Found {len(segments)} mandatory segments.")
    import json
    print(json.dumps(segments[:2], indent=2))
    
    # 2. Mapping
    engine = MappingEngine856(client)
    erp_path = input_dir / "856_ERP_Definitions.xlsx"
    engine.load_definitions(str(erp_path))
    
    mapping = engine.generate_mapping(segments)
    print("Mapping Result (Sample):")
    print(json.dumps(mapping.get("mappings", [])[:3], indent=2))
    
    # 3. Excel Build
    from src.flow_856.excel_builder import ExcelBuilder856
    builder = ExcelBuilder856()
    output_path = builder.build_excel(mapping, "output")
    print(f"Generated Excel: {output_path}")

if __name__ == "__main__":
    test_flow()
