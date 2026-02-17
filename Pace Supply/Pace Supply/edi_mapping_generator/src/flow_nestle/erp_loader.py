"""
ERP Loader Module.
Reads GLB_RGTX_ORDERSCPG_COMPLETE.xlsx — the client's SAP IDoc field definitions.
Returns all 651+ ERP fields as a list of dicts.
"""
import pandas as pd
from typing import List, Dict, Any
from pathlib import Path
from logger import get_logger


class ErpLoader:
    """Loads SAP IDoc ERP field definitions from the generated Excel file."""

    REQUIRED_COLS = [
        "Segment name", "Segment description", "Status",
        "Element name", "Element description", "Data type",
        "Internal length", "Position in segment", "Offset", "External length"
    ]

    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.logger = get_logger()

    def load(self) -> List[Dict[str, Any]]:
        """
        Reads the ERP definition Excel and returns a flat list of field dicts.
        Each dict represents one SAP IDoc element (field).
        """
        path = Path(self.excel_path)
        if not path.exists():
            self.logger.error(f"ERP file not found: {self.excel_path}")
            return []

        try:
            df = pd.read_excel(self.excel_path)
            df.columns = [c.strip() for c in df.columns]

            # Validate required columns
            missing = [c for c in self.REQUIRED_COLS if c not in df.columns]
            if missing:
                self.logger.error(f"ERP file missing columns: {missing}")
                return []

            # Fill NaN with empty string for text cols
            for col in df.columns:
                df[col] = df[col].fillna("")

            records = []
            for _, row in df.iterrows():
                records.append({
                    "sap_segment": str(row["Segment name"]).strip(),
                    "sap_segment_desc": str(row["Segment description"]).strip(),
                    "sap_status": str(row["Status"]).strip(),
                    "sap_field": str(row["Element name"]).strip(),
                    "sap_field_desc": str(row["Element description"]).strip(),
                    "sap_data_type": str(row["Data type"]).strip(),
                    "sap_internal_length": str(row["Internal length"]).strip(),
                    "sap_position": str(row["Position in segment"]).strip(),
                    "sap_offset": str(row["Offset"]).strip(),
                    "sap_external_length": str(row["External length"]).strip(),
                })

            self.logger.info(f"Loaded {len(records)} ERP fields from {path.name}")
            return records

        except Exception as e:
            self.logger.error(f"Failed to load ERP file: {e}")
            return []
