"""
Mapping Service
Decouples logic from CLI main.py to allow API usage.
"""
from typing import Dict, Any, List
import shutil
import tempfile
import os
import yaml
from dotenv import load_dotenv
from pathlib import Path
from record_processor import RecordProcessor
from ai_client import AIClient
from pdf_constraint_extractor import PdfConstraintExtractor
from edi_parser import parse_edi_file
from excel_reader import read_erp_structure
from excel_writer import write_mapping_output
from logger import get_logger

# 856 Imports
from src.flow_856.pdf_processor import PdfProcessor856
from src.flow_856.mapping_engine import MappingEngine856
from src.flow_856.excel_builder import ExcelBuilder856

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

logger = get_logger()

class MappingService:
    def __init__(self):
        # Load config from parent dir
        config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config not found at {config_path}")
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.ai_client = AIClient(
            base_url=config["llm_base_url"],
            api_key=config["llm_api_key"],
            model=config["llm_model"],
            timeout=config.get("timeout", 120),
            max_retries=config.get("max_retries", 3),
            auth_type=config.get("auth_type", "bearer"),
            auth_header_name=config.get("auth_header_name")
        )
        self.pdf_parser = PdfConstraintExtractor(self.ai_client)
        # Store sessions in memory for now
        self.sessions: Dict[str, Any] = {}

    def create_session(self, edi_content: str, pdf_path: str) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        
        self.sessions[session_id] = {
            "edi_content": edi_content,
            "pdf_path": pdf_path,
            "status": "ready",
            "mappings": {},
            "output_file": None
        }
        return session_id

    def generate_mapping(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Invalid Session")

        session["status"] = "processing"
        
        # 1. Parse EDI
        edi_parsed = parse_edi_file(session["edi_content"])
        
        # 2. Parse PDF
        constraints = self.pdf_parser.extract_constraints(session["pdf_path"])
        
        from excel_reader import read_full_sheet_data
        
        # 3. Read Full Grid for UI (Spreadsheet View)
        # Check env var first
        env_erp_path = os.getenv("ERP_DEFINITION_PATH")
        base_dir = Path(__file__).parent.parent
        
        erp_files = []
        if env_erp_path:
             # Handle relative paths from root
             p = Path(env_erp_path)
             if not p.is_absolute():
                 p = base_dir / p
             erp_files.append(p)

        # Fallbacks
        erp_files.append(base_dir / "input" / "inbound_X12_to_oracle.xlsx")
        erp_files.append(base_dir / "inbound_X12_to_oracle.xlsx")
        erp_files.append(base_dir / "ERP_Definition.xlsx")
        
        erp_file = None
        for f in erp_files:
            if f.exists():
                erp_file = f
                break
                
        if not erp_file:
             # Fallback to local check if run directly
             if Path("inbound_X12_to_oracle.xlsx").exists():
                 erp_file = Path("inbound_X12_to_oracle.xlsx")
             else:
                 raise FileNotFoundError(f"Mapping template file not found. Searched in: {[str(f) for f in erp_files]}")
             
        full_grid = read_full_sheet_data(str(erp_file))
        structure = read_erp_structure(str(erp_file))
        
        # 4. Processor
        processor = RecordProcessor(self.ai_client, edi_parsed, constraints)
        
        mappings = {}
        for rec_id, fields in structure.items():
            rec_map = processor.process_record(rec_id, fields)
            mappings[rec_id] = rec_map
            
        # 5. Merge AI results into full grid for UI
        # We need to find the correct rows in the grid and update Col B (idx 1), Col C (idx 2)
        # Note: read_full_sheet_data returns 1-indexed (via iter_rows), 
        # but our list is 0-indexed. row_idx from read_erp_structure is 1-indexed.
        for rec_id, field_maps in mappings.items():
            rows_to_update = structure.get(rec_id, [])
            for field_info in rows_to_update:
                field_name = field_info["field_name"]
                row_idx = field_info["row_idx"] # 1-indexed
                
                if field_name in field_maps:
                    ai_vals = field_maps[field_name]
                    # col B (index 1), col C (index 2)
                    # Python list index is row_idx - 1
                    list_row_idx = row_idx - 1
                    if list_row_idx < len(full_grid):
                        full_grid[list_row_idx][1] = ai_vals.get("B")
                        full_grid[list_row_idx][2] = ai_vals.get("C")

        session["mappings"] = mappings
        session["grid"] = full_grid
        session["structure"] = structure 
        session["status"] = "completed"
        
        return {"grid": full_grid, "mappings": mappings}

    def update_mapping(self, session_id: str, rec_id: str, field_name: str, updates: Dict[str, str]):
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Invalid Session")
            
        if rec_id not in session["mappings"]:
            session["mappings"][rec_id] = {}
            
        # Update specific field
        # We expect updates to contain keys 'B', 'C'
        current = session["mappings"][rec_id].get(field_name, {})
        current.update(updates)
        session["mappings"][rec_id][field_name] = current
        
        return current

    def create_session_856(self, pdf_path: str) -> str:
        """Create a session for 856 flow (PDF only)."""
        import uuid
        session_id = str(uuid.uuid4())
        
        self.sessions[session_id] = {
            "type": "856",
            "pdf_path": pdf_path,
            "status": "ready",
            "mappings": {},
            "grid": [], # Will populate after generation
            "output_file": None
        }
        return session_id

    def generate_mapping_856(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session or session.get("type") != "856":
            raise ValueError("Invalid 856 Session")

        session["status"] = "processing"
        
        # 1. Extract Constraints
        proc = PdfProcessor856(self.ai_client)
        segments = proc.extract_mandatory_segments(session["pdf_path"])
        
        # 2. Map fields
        engine = MappingEngine856(self.ai_client)
        # Load Definitions - Need to locate file
        # Assuming typical location
        # Try both 856 subdir and input dir
        base_dir = Path(__file__).parent.parent
        erp_def_path = base_dir / "856" / "856_ERP_Definitions.xlsx"
        if not erp_def_path.exists():
             # fallback
             erp_def_path = base_dir / "input" / "856_ERP_Definitions.xlsx"
             
        if not erp_def_path.exists():
             raise FileNotFoundError(f"856_ERP_Definitions.xlsx not found")
             
        engine.load_definitions(str(erp_def_path))
        mapping_result = engine.generate_mapping(segments)
        
        session["mappings"] = mapping_result # Store full result { mappings: [...] }
        
        # 3. Build Grid for Frontend
        # Frontend expects [[col1, col2...], ...]
        # Mimic new Excel Structure (A-H)
        # Seg, Occ, Element, Type, Source, Hardcode, Meaning, Req
        grid = []
        # Header
        grid.append(["Seg.", "Occ.", "Element", "Type", "Source (Mapping)", "Hardcode", "Meaning", "Req"])
        
        last_segment = None
        
        for item in mapping_result.get("mappings", []):
            segment = item.get("segment", "")
            element = item.get("element", "")
            
            # Grouping Logic for display
            disp_seg = segment
            if segment == last_segment:
                disp_seg = ""
            else:
                last_segment = segment
            
            occ = ""
            
            # Type/Source/Hardcode Login
            rec = item.get("erp_record", "")
            field = item.get("erp_field", "")
            pos = item.get("erp_position", "")
            
            typ = item.get("type", "")
            hardcode = item.get("hardcode", "")
            meaning = ""
            
            # Logic to populate grid columns
            source = ""
            if typ == "Source":
                if rec and field:
                    source = f"{rec}/{pos if pos else '???'}"
                    meaning = field
            elif typ == "Translation":
                # Translation: Meaning = Desc, Hardcode = Codes, Source = Rec/Pos
                meaning = item.get("logic", "") + " " + item.get("description", "")
                if rec and field:
                     source = f"{rec}/{pos if pos else '???'}"
            elif typ == "Constant":
                meaning = item.get("logic", "") + " " + item.get("description", "")
                pass 
            else:
                 # Sequence, Inherit, Count
                 meaning = item.get("logic", "")
                 
            # Fallback if meaning empty
            if not meaning:
                meaning = item.get("logic", "")

            # Persist inferred state to item for editing/export
            req = "Mandatory"
            
            grid.append([disp_seg, occ, element, typ, source, hardcode, meaning, req])
            
        session["grid"] = grid
        session["status"] = "completed"
        return {"grid": grid, "mappings": mapping_result}

    def generate_excel(self, session_id: str) -> str:
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Invalid Session")

        if session.get("type") == "856":
            # Use 856 Builder
            mappings = session["mappings"]
            builder = ExcelBuilder856(template_path="856/PaceSupply_856_Outbound.xlsx")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                output_path = tmp.name
                
            final_path = builder.build_excel(mappings, str(Path(output_path).parent))
            session["output_file"] = final_path
            return final_path
        else:
            # Existing 850 Logic
            # Create temp output
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                output_path = tmp.name
                
            # Write
            final_path = write_mapping_output(
                session["structure"],
                session["mappings"],
                str(Path(output_path).parent)
            )
            
            session["output_file"] = final_path
            return final_path
