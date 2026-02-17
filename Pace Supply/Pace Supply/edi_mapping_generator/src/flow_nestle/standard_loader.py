"""
Standard Loader Module.
Reads EDI850_to_ORDERS05_Mapping_Standard.xlsx — the known X12 ↔ SAP IDoc mappings.
Provides both forward (X12→SAP) and reverse (SAP→X12) lookups.
"""
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from logger import get_logger


class StandardLoader:
    """
    Loads the Standard 850↔ORDERS05 Mapping from Excel.
    Provides forward and reverse lookups.
    """

    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.logger = get_logger()
        self.mappings: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Reverse index: (SAP_Segment, SAP_Field) → List of X12 mapping dicts
        self._reverse_index: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    def load(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """
        Reads the Excel file and builds both forward and reverse lookup dicts.
        Returns: Dict[(X12_Segment, X12_Element), { ...mapping_details... }]
        """
        if not Path(self.excel_path).exists():
            self.logger.error(f"Standard Mapping File not found: {self.excel_path}")
            return {}

        try:
            df = pd.read_excel(self.excel_path, sheet_name='Mapping')
            df.columns = [c.strip() for c in df.columns]

            for _, row in df.iterrows():
                seg = str(row.get('X12_Segment', '')).strip()
                elem = str(row.get('X12_Element', '')).strip()

                if not seg or not elem:
                    continue

                sap_seg = str(row.get('SAP_IDoc_Segment', '')).strip()
                sap_field = str(row.get('SAP_Field', '')).strip()

                mapping_info = {
                    "x12_segment": seg,
                    "x12_element": elem,
                    "description": str(row.get('Element_Description', '')).strip(),
                    "sap_segment": sap_seg,
                    "sap_field": sap_field,
                    "mapping_rule": str(row.get('Mapping_Rule', '')).strip(),
                    "notes": str(row.get('Notes', '')).strip()
                }

                # Forward: (X12_Seg, X12_Elem) → mapping
                key = (seg, elem)
                self.mappings[key] = mapping_info

                # Reverse: (SAP_Segment, SAP_Field) → list of mappings
                if sap_seg and sap_field:
                    rev_key = (sap_seg, sap_field)
                    if rev_key not in self._reverse_index:
                        self._reverse_index[rev_key] = []
                    self._reverse_index[rev_key].append(mapping_info)

            self.logger.info(
                f"Loaded {len(self.mappings)} standard mappings "
                f"({len(self._reverse_index)} reverse keys) from {self.excel_path}"
            )
            return self.mappings

        except Exception as e:
            self.logger.error(f"Failed to load standard mappings: {e}")
            return {}

    def get_by_sap_field(self, sap_segment: str, sap_field: str) -> List[Dict[str, Any]]:
        """
        Reverse lookup: given a SAP segment+field, return all known X12 mappings.
        Returns an empty list if no mapping is found.
        """
        return self._reverse_index.get((sap_segment, sap_field), [])

    def get_all_reverse_mappings(self) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Return the full reverse index."""
        return self._reverse_index


if __name__ == "__main__":
    import sys
    loader = StandardLoader(sys.argv[1] if len(sys.argv) > 1 else "EDI850_to_ORDERS05_Mapping_Standard.xlsx")
    m = loader.load()
    print(f"Loaded {len(m)} forward items, {len(loader._reverse_index)} reverse keys.")
    # Test reverse lookup
    test = loader.get_by_sap_field("E1EDK01", "ACTION")
    print(f"Reverse lookup E1EDK01/ACTION: {test}")
