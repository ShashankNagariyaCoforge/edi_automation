"""
Nestle Flow Service — Orchestrates the redesigned Nestle 850 flow.

Flow:
  1. Load ERP fields from GLB_RGTX_ORDERSCPG_COMPLETE.xlsx
  2. Load Standard X12↔SAP mappings from EDI850_to_ORDERS05_Mapping_Standard.xlsx
  3. Extract ALL segments from vendor PDF via AI
  4. Run Gap Analysis → produce 16-column grid
"""
from typing import Dict, Any, List
import uuid
import os
from pathlib import Path

from .erp_loader import ErpLoader
from .standard_loader import StandardLoader
from .gap_analyzer import GapAnalyzer
from logger import get_logger
from pdf_constraint_extractor import PdfConstraintExtractor


class NestleService:
    """Orchestrates the Nestle 850 Flow."""

    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.logger = get_logger()

        base_path = os.getcwd()
        if "src" in base_path:
            base_path = os.path.dirname(base_path)

        # --- Load ERP fields ---
        erp_path = os.path.join(base_path, "GLB_RGTX_ORDERSCPG_COMPLETE.xlsx")
        self.erp_loader = ErpLoader(erp_path)
        self.erp_fields = self.erp_loader.load()
        self.logger.info(f"ERP fields loaded: {len(self.erp_fields)}")

        # --- Load Standard Mapping (with reverse lookup) ---
        std_path = os.path.join(base_path, "EDI850_to_ORDERS05_Mapping_Standard.xlsx")
        self.standard_loader = StandardLoader(std_path)
        self.standard_loader.load()

        # --- PDF Extractor ---
        self.pdf_extractor = PdfConstraintExtractor(ai_client)

        # Sessions
        self.sessions: Dict[str, Dict] = {}

    def create_session(self, pdf_path: str) -> str:
        """Create a new session for a Nestle 850 mapping task."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "type": "nestle_850",
            "pdf_path": pdf_path,
            "status": "created",
            "grid": [],
            "mappings": {},
        }
        self.logger.info(f"Created Nestle session: {session_id}")
        return session_id

    def generate_mapping(self, session_id: str) -> Dict[str, Any]:
        """
        Run the full flow:
          PDF Extract (all segments) → Gap Analysis → AI Match → Value Flagging → Grid
        Returns: {"grid": [...], "flags": {...}}
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")

        pdf_path = session["pdf_path"]

        # 1. Extract ALL segments from the vendor PDF
        self.logger.info(f"Extracting ALL segments from {pdf_path}...")
        pdf_segments = self.pdf_extractor.extract_all_segments(pdf_path)
        self.logger.info(f"PDF extraction returned {len(pdf_segments)} segments")

        # 2. Gap Analysis (ERP-centric)
        self.logger.info("Running ERP-centric Gap Analysis...")
        analyzer = GapAnalyzer(
            standard_loader=self.standard_loader,
            pdf_segments=pdf_segments,
            ai_client=self.ai_client,
        )
        grid_rows, flags = analyzer.analyze(self.erp_fields)

        # 3. Update Session
        session["grid"] = grid_rows
        session["flags"] = flags
        session["status"] = "generated"

        return {"grid": grid_rows, "flags": flags}

    def get_session(self, session_id: str):
        return self.sessions.get(session_id)

    def generate_excel(self, session_id: str) -> str:
        """Generate an Excel file from the current grid state."""
        import pandas as pd
        import tempfile

        session = self.sessions.get(session_id)
        if not session or "grid" not in session:
            raise ValueError("Invalid Session or no grid generated")

        grid = session["grid"]
        if not grid:
            raise ValueError("Grid is empty")

        # Grid[0] is headers
        df = pd.DataFrame(grid[1:], columns=grid[0])

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            output_path = tmp.name

        df.to_excel(output_path, index=False)
        self.logger.info(f"Generated Nestle Excel at {output_path}")
        return output_path
