from typing import Dict, Any, List
import uuid
import os
from .standard_loader import StandardLoader
from .gap_analyzer import GapAnalyzer
from logger import get_logger
from pdf_constraint_extractor import PdfConstraintExtractor

class NestleService:
    """
    Orchestrates the Nestle 850 Flow.
    """
    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.logger = get_logger()
        # Initialize sub-components
        # We assume the standard file is in the project root relative to execution
        # Or hardcoded path. For now, let's look in current directory or parent.
        # Based on user context: /home/azureuser/Documents/projects/edi_automation/edi_automation/Pace Supply/Pace Supply/edi_mapping_generator/EDI850_to_ORDERS05_Mapping_Standard.xlsx
        
        base_path = os.getcwd()
        if "src" in base_path:
            base_path = os.path.dirname(base_path)
            
        std_path = os.path.join(base_path, "EDI850_to_ORDERS05_Mapping_Standard.xlsx")
        
        self.loader = StandardLoader(std_path)
        self.standard_mappings = self.loader.load()
        self.gap_analyzer = GapAnalyzer(self.standard_mappings)
        self.pdf_extractor = PdfConstraintExtractor(ai_client)
        
        # In-memory session storage (simple dict for now)
        self.sessions = {}

    def create_session(self, pdf_path: str) -> str:
        """
        Creates a new session for a Nestle 850 mapping task.
        """
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "type": "nestle_850",
            "pdf_path": pdf_path,
            "status": "created",
            "grid": [],
            "mappings": {}
        }
        self.logger.info(f"Created Nestle session: {session_id}")
        return session_id

    def generate_mapping(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Runs the full flow: PDF Extract -> Gap Analysis -> Grid Generation
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")
            
        pdf_path = session["pdf_path"]
        
        # 1. Extract PDF Constraints (Using existing Logic)
        self.logger.info(f"Extracting constraints from {pdf_path}...")
        constraints = self.pdf_extractor.extract_constraints(pdf_path)
        
        # 2. Gap Analysis
        self.logger.info("Running Gap Analysis...")
        grid_rows = self.gap_analyzer.analyze(constraints)
        
        # 3. Update Session
        session["grid"] = grid_rows
        session["status"] = "generated"
        
        return grid_rows

    def get_session(self, session_id: str):
        return self.sessions.get(session_id)

    def generate_excel(self, session_id: str) -> str:
        """
        Generates an Excel file from the current grid state.
        """
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
