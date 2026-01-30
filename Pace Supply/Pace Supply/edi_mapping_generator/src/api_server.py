from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import shutil
import os
import tempfile
from mapping_service import MappingService

app = FastAPI(title="EDI Mapping Dashboard API")

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = MappingService()

class UpdateMappingRequest(BaseModel):
    row_idx: int
    col_idx: int
    value: str

@app.post("/api/upload")
async def upload_files(edi_file: UploadFile = File(...), pdf_file: UploadFile = File(...)):
    # Read EDI content
    edi_content = (await edi_file.read()).decode("utf-8")
    
    # Save PDF temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(pdf_file.file, tmp)
        pdf_path = tmp.name
        
    session_id = service.create_session(edi_content, pdf_path)
    return {"session_id": session_id}

@app.post("/api/generate/{session_id}")
async def generate_mappings(session_id: str):
    try:
        mappings = service.generate_mapping(session_id)
        return {"status": "success", "mappings": mappings, "version": "v1.0.1_spreadsheet_fix"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mappings/{session_id}")
async def get_mappings(session_id: str):
    session = service.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "mappings": session.get("mappings", {}),
        "grid": session.get("grid", [])
    }

@app.post("/api/856/upload")
async def upload_files_856(pdf_file: UploadFile = File(...)):
    # Save PDF temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(pdf_file.file, tmp)
        pdf_path = tmp.name
        
    session_id = service.create_session_856(pdf_path)
    return {"session_id": session_id}

@app.post("/api/856/generate/{session_id}")
async def generate_mappings_856(session_id: str):
    try:
        result = service.generate_mapping_856(session_id)
        # Flatten mappings if needed or return as is. 
        # service returns {"grid": ..., "mappings": ...}
        return {"status": "success", "mappings": result, "version": "v1.0.856"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/mappings/{session_id}/update")
async def update_mapping_field(session_id: str, request: UpdateMappingRequest):
    try:
        session = service.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        grid = session.get("grid")
        if not grid or request.row_idx >= len(grid):
             raise HTTPException(status_code=400, detail="Invalid row index")
             
        if request.col_idx >= len(grid[request.row_idx]):
             raise HTTPException(status_code=400, detail="Invalid column index")

        # 1. Update Grid
        grid[request.row_idx][request.col_idx] = request.value
        
        # 2. Sync to Mappings
        session_type = session.get("type", "850")
        
        if session_type == "856":
            # For 856, Mapping is a list: session['mappings']['mappings']
            # row_idx includes header (0). So data index is row_idx - 1.
            data_idx = request.row_idx - 1
            if 0 <= data_idx < len(session["mappings"].get("mappings", [])):
                item = session["mappings"]["mappings"][data_idx]
                
                # New Column Map:
                # 0: Seg, 1: Occ, 2: Elem, 3: Type, 4: Source, 5: Hardcode, 6: Meaning, 7: Req
                
                if request.col_idx == 3:
                     item["type"] = request.value
                elif request.col_idx == 5:
                     item["hardcode"] = request.value
                elif request.col_idx == 6:
                     item["logic"] = request.value
                elif request.col_idx == 4:
                    # Parse "0010/80 - FieldName"
                    val = request.value
                    if "/" in val and "-" in val:
                         # Try to parse roughly
                         try:
                             rec_pos, field = val.split("-", 1)
                             rec, pos = rec_pos.strip().split("/", 1)
                             item["erp_record"] = rec.strip()
                             item["erp_position"] = pos.strip()
                             item["erp_field"] = field.strip()
                             # Also set type to Source if valid map
                             item["type"] = "Source"
                         except:
                             pass
                    elif val.strip() == "":
                        # clear mapping
                        item["erp_record"] = ""
                        item["erp_field"] = ""
                        item["erp_position"] = ""
        
        # 850 Logic
        elif request.col_idx in [1, 2]:
            col_key = "B" if request.col_idx == 1 else "C"
            row_num = request.row_idx + 1 # 1-indexed for matching structure
            
            # Find which record/field this row belongs to
            structure = session.get("structure", {})
            mappings = session.get("mappings", {})
            
            found = False
            for rec_id, fields in structure.items():
                for field_info in fields:
                    if field_info["row_idx"] == row_num:
                        field_name = field_info["field_name"]
                        if rec_id not in mappings:
                            mappings[rec_id] = {}
                        if field_name not in mappings[rec_id]:
                            mappings[rec_id][field_name] = {}
                        
                        mappings[rec_id][field_name][col_key] = request.value
                        found = True
                        break
                if found: break
                
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download/{session_id}")
async def download_excel(session_id: str):
    try:
        path = service.generate_excel(session_id)
        from fastapi.responses import FileResponse
        return FileResponse(path, filename="all_mappings.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
