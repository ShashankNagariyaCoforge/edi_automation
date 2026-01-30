from pathlib import Path
from openpyxl import load_workbook
from typing import Dict, Any, List
import shutil
import time

class ExcelBuilder856:
    """
    Builds the 856 Output Excel file.
    Follows format of 'PaceSupply_856_Outbound.xlsx'.
    """
    
    def __init__(self, template_path: str = "856/PaceSupply_856_Outbound.xlsx"):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            # Fallback path logic if needed
            pass
            
    def build_excel(self, mappings: Dict[str, Any], output_path: str) -> str:
        """
        Populate the template with mappings.
        mappings structure: 
        { 
          "mappings": [ 
             { "segment": "BSN", "element": "BSN01", "erp_record": "0010", "erp_field": "DOC...", "logic": "..." } 
          ]
        }
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        final_path = Path(output_path) / f"856_Mapping_{timestamp}.xlsx"
        
        # Copy template
        shutil.copy(self.template_path, final_path)
        
        wb = load_workbook(final_path)
        if "ANSI X12 Mapping" in wb.sheetnames:
            ws = wb["ANSI X12 Mapping"]
        else:
            ws = wb.active
            
        # The user said: "output file should have exactly those columns as in this sheet"
        # "input file PaceSupply_856_Outbound.xlsx in sheet 'ANSI X12 Mapping'"
        # Columns:
        # A: Field Name (Segment + Element + Description)
        # B, C, D... 
        # E: Mapping (Record/Position)
        
        # We need to find rows corresponding to the Segments we found.
        # But wait, the Template likely already HAS rows for segments.
        # OR we need to Append?
        # The user said: "wherever we have mandatory mentioned in segments all of those segments we need to put in mapping output file."
        # This implies we might need to CLEAR the sheet and write fresh, OR append.
        # But if we use it as a template, maybe it has a header?
        # Let's assume we append to the end of the sheet or overwrite if logic permits.
        
        # Strategy:
        # 1. Clear existing data rows (keep header).
        # 2. Write each mandatory segment/field.
        
        # Header Row is 1. Start data at 2.
        # Template Columns:
        # A (1): Seg.
        # B (2): Occ./Max
        # C (3): Element
        # D (4): Type ('Source' or 'Constant')
        # E (5): Source (Mapping)
        # F (6): Hardcode
        # G (7): Meaning (Description)
        # H (8): Optional/Mandatory
        
        start_row = 2
        mapped_data = mappings.get("mappings", [])
        
        last_segment = None
        
        for i, item in enumerate(mapped_data):
            row_idx = start_row + i
            
            # 1. Segment (Col A) - Grouping logic
            segment = item.get("segment", "")
            if segment == last_segment:
                ws.cell(row=row_idx, column=1, value=None)
            else:
                ws.cell(row=row_idx, column=1, value=segment)
                last_segment = segment
                
            # 2. Occ/Max (Col B) - Not currently extracted, leave blank or default
            # ws.cell(row=row_idx, column=2, value="")
            
            # 3. Element (Col C) - e.g. ST01
            element = item.get("element", "")
            # Ensure we show the full code if not present. item['element'] usually is 'ST01'
            ws.cell(row=row_idx, column=3, value=element)
            
            # 6. Description (Col G)
            # This corresponds to "Meaning" in template
            desc = item.get("logic", "")
            # Clean up "Direct Map - " prefix if present? The user template has "Meaning" blank in row 2...
            # But earlier user said "Description". Let's put it in G.
            ws.cell(row=row_idx, column=7, value=desc)
            
            # 7. Requirement (Col H)
            # We don't have this explicitly in 'mappings' dict from Engine, 
            # BUT we might have it if we passed it through.
            # The Engine takes 'mandatory_segments'.
            # We can default to 'M' since we only extracted Mandatory.
            ws.cell(row=row_idx, column=8, value="Mandatory")
            
            # MAPPING LOGIC (Type, Source, Hardcode)
            # Prefer explicit values from item (if edited or inferred and stored)
            typ = item.get("type", "")
            hardcode = item.get("hardcode", "")
            
            rec = item.get("erp_record", "")
            field = item.get("erp_field", "")
            pos = item.get("erp_position", "")

            # If type is explicit, use it.
            if typ:
                ws.cell(row=row_idx, column=4, value=typ)
                
                if typ == "Source":
                     # Col E: just record/pos
                     if rec and pos:
                         map_rec_pos = f"{rec}/{pos}"
                         ws.cell(row=row_idx, column=5, value=map_rec_pos)
                         
                     # Col G (Meaning): ERP Field Name
                     ws.cell(row=row_idx, column=7, value=field)
                     
                elif typ in ["Constant", "Translation"]:
                     # Col F: Hardcode
                     ws.cell(row=row_idx, column=6, value=hardcode)
                     # Col G (Meaning): Description
                     ws.cell(row=row_idx, column=7, value=desc)
                     
                     if typ == "Translation" and rec and pos:
                         # Translation also needs Source Mapping
                         ws.cell(row=row_idx, column=5, value=f"{rec}/{pos}")
                     
                else:
                     # Sequence, Inherit, Count
                     # Col G (Meaning): Description
                     ws.cell(row=row_idx, column=7, value=desc)

            else:
                # Fallback logic if Type not present (shouldn't happen with new Engine logic)
                ws.cell(row=row_idx, column=7, value=desc) # Fallback meaning
                
                if rec and field:
                    ws.cell(row=row_idx, column=4, value="Source")
                    ws.cell(row=row_idx, column=5, value=f"{rec}/{pos}")
                    ws.cell(row=row_idx, column=7, value=field)
                else:
                    pass

        wb.save(final_path)
        return str(final_path)
