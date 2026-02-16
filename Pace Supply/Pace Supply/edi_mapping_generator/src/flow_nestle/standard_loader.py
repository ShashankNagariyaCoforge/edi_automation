import pandas as pd
from typing import Dict, Any, List
from pathlib import Path
from logger import get_logger

class StandardLoader:
    """
    Loads the Standard Nestle 850 Mapping from Excel.
    """
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.logger = get_logger()
        self.mappings = {} # Key: (Segment, Element) -> Mapping Dict

    def load(self) -> Dict[tuple, Dict[str, Any]]:
        """
        Reads the Excel file and builds a lookup dictionary.
        Returns: Dict[(Segment, Element), { ...mapping_details... }]
        """
        if not Path(self.excel_path).exists():
            self.logger.error(f"Standard Mapping File not found: {self.excel_path}")
            return {}

        try:
            df = pd.read_excel(self.excel_path, sheet_name='Mapping')
            
            # Normalize headers just in case
            df.columns = [c.strip() for c in df.columns]
            
            # Iterate and build lookup
            for _, row in df.iterrows():
                seg = str(row.get('X12_Segment', '')).strip()
                elem = str(row.get('X12_Element', '')).strip()
                
                if not seg or not elem:
                    continue
                    
                # Key = (Segment, Element) e.g. ("BEG", "BEG03")
                key = (seg, elem)
                
                mapping_info = {
                    "x12_segment": seg,
                    "x12_element": elem,
                    "description": str(row.get('Element_Description', '')).strip(),
                    "sap_segment": str(row.get('SAP_IDoc_Segment', '')).strip(),
                    "sap_field": str(row.get('SAP_Field', '')).strip(),
                    "mapping_rule": str(row.get('Mapping_Rule', '')).strip(),
                    "notes": str(row.get('Notes', '')).strip()
                }
                
                self.mappings[key] = mapping_info
                
            self.logger.info(f"Loaded {len(self.mappings)} standard mappings from {self.excel_path}")
            return self.mappings
            
        except Exception as e:
            self.logger.error(f"Failed to load standard mappings: {e}")
            return {}

if __name__ == "__main__":
    # Test Run
    import sys
    loader = StandardLoader(sys.argv[1] if len(sys.argv) > 1 else "EDI850_to_ORDERS05_Mapping_Standard.xlsx")
    m = loader.load()
    print(f"Loaded {len(m)} items.")
    if m:
        first_key = list(m.keys())[0]
        print(f"Sample {first_key}: {m[first_key]}")
