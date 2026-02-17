"""
Agent Engine for EDI Copilot.
Handles the Agentic Loop: Perceive -> Think -> Act.
"""
import json
import traceback
from typing import Dict, Any, Generator, List, Callable
from logger import get_logger
from ai_client import AIClient

class AgentEngine:
    def __init__(self, ai_client: AIClient, mapping_service: Any):
        self.ai_client = ai_client
        self.mapping_service = mapping_service
        self.logger = get_logger()

    def run_agent_loop(self, session_id: str, user_query: str) -> Generator[str, None, None]:
        # 1. State Retrieval
        session = self.mapping_service.sessions.get(session_id)
        if not session:
            yield json.dumps({"type": "error", "content": "Session not found."})
            return

        # Initialize history
        if "chat_history" not in session:
            session["chat_history"] = []

        # 2. Build Initial Context
        
        history_str = ""
        for msg in session["chat_history"][-5:]:
            history_str += f"{msg['role'].upper()}: {msg['content']}\n"
            
        context_str = f"""
PREVIOUS CONVERSATION:
{history_str}

CURRENT QUERY:
User: {user_query}
"""
        
        system_prompt = """You are an Agentic EDI Copilot.
TOOLS AVAILABLE:
1. READ_GRID: Returns the first 10 rows of the grid (Header + Data). Use this to see column names and values.
2. SEARCH_SPEC: Queries the Vendor PDF Spec.
3. UPDATE_ROW: Updates a specific cell. Format: UPDATE_ROW(row_idx, col_idx, value). row_idx is 0-indexed.
4. EXPLAIN_EDI: General knowledge.
5. GET_NESTLE_FLAGS: Returns all rows where the Mapping Rule column is flagged because the PDF specifies values not covered by the mapping rule. Each flag includes the row index, X12 element, and a reason explaining the discrepancy.

PROTOCOL:
1. THINK: Analyze the request.
2. ACTION: Should I use a tool?
   - If YES -> Output "ACTION: [ToolName] [Args]"
   - If NO -> Output "ANSWER: [Response]"
   
Constraint: Only ONE Action per turn. Wait for OBSERVATION.
IMPORTANT: When using UPDATE_ROW, use the format: `UPDATE_ROW [RowIndex] [ColIndex] [ElementTag] [Value]`
Example: `UPDATE_ROW 5 3 BEG03 00`
You MUST verify the RowIndex matches the ElementTag (e.g. BEG03) you see in the READ_GRID output. The system will reject updates if they do not match.
    - SEARCH_SPEC [Query]: Searches the PDF specification for answers.
    - GET_FLAGGED_ROWS: Returns a list of all rows that are highlighted in RED (Validation Errors). Use this to identify what needs fixing.
    - GET_NESTLE_FLAGS: Returns all ORANGE-flagged rows with PDF value discrepancies.

VISUAL INDICATORS:
- If the READ_GRID output shows `[FLAGGED: ...]` next to a row, this means the row is HIGHLIGHTED IN RED in the user interface due to a validation error. Explicitly mention "highlighted in red" when discussing these fields.
- ORANGE-highlighted cells in the Mapping Rule column indicate that the vendor PDF specifies value codes not covered by the standard mapping rule. Use GET_NESTLE_FLAGS to see these.
"""
        
        # We allow up to 7 turns (Think -> Act -> Observe -> Think -> Act -> Observe -> Answer)
        max_turns = 7
        current_context = context_str
        
        full_interaction_log = ""
        final_answer_text = ""

        # Initial Prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_context}
        ]
        
        for turn in range(max_turns):
            # Stream LLM Response
            yield json.dumps({"type": "thought", "content": f"\n--- Step {turn+1} ---\n"})

            buffer = ""
            action_found = False
            action_name = ""
            action_args = ""
            
            # Streaming loop for THIS turn
            stream = self.ai_client.stream_completion_messages(messages)
            
            for chunk in stream:
                buffer += chunk
                
                # Check for ACTION
                if "ACTION:" in buffer and not action_found:
                    # We detected an action starting.
                    pass

                # Output to UI
                # Heuristic: If we haven't seen "ANSWER:", send as thought.
                if "ANSWER:" in buffer:
                    # Send only the new part as message
                    clean_chunk = chunk 
                    if "ANSWER:" in chunk:
                         clean_chunk = chunk.split("ANSWER:")[-1]
                    yield json.dumps({"type": "message", "content": clean_chunk})
                    final_answer_text += clean_chunk
                else:
                    yield json.dumps({"type": "thought", "content": chunk})

            # End of Turn Processing
            full_interaction_log += buffer
            messages.append({"role": "assistant", "content": buffer})
            
            # Parse Action
            import re
            # Regex to find ACTION: ToolName Args
            # We look for the LAST action in the buffer
            match = re.search(r"ACTION:\s*(\w+)(.*)", buffer, re.DOTALL)
            
            if "ANSWER:" in buffer:
                # We are done.
                break
                
            if match:
                action_found = True
                action_name = match.group(1).strip()
                action_args = match.group(2).strip()
                
                yield json.dumps({"type": "thought", "content": f"\nCreate Tool: {action_name}..."})
                
                # Execute Tool
                observation = f"Error: Tool {action_name} not found."
                
                if action_name == "READ_GRID":
                    observation = self._tool_read_grid(session_id)
                elif action_name == "UPDATE_ROW":
                    # Expecting: UPDATE_ROW ROW COL TAG VALUE
                    # Example: UPDATE_ROW 3 5 REF01 "07"
                    # Supports space or comma delimited.
                    
                    # Normalize: replace commas with spaces, then split
                    clean_args = action_args.replace(",", " ").replace("(", " ").replace(")", " ")
                    parts = clean_args.split(None, 3) # Split into at most 4 parts
                    
                    if len(parts) < 4:
                        observation = "Error: Invalid arguments. Usage: UPDATE_ROW [RowIdx] [ColIdx] [ElementTag] [Value]"
                    else:
                        try:
                            # Parse args
                            r = int(parts[0])
                            c = int(parts[1])
                            tag = parts[2] # element tag
                            v = parts[3].strip("'\"") # value
                            
                            observation = self._tool_update_row(session_id, r, c, tag, v)
                        except Exception as e:
                             observation = f"Error processing arguments: {str(e)}"
                        
                elif action_name == "SEARCH_SPEC":
                     # Use "run_agent_loop" parsing logic or passed args?
                     # SEARCH_SPEC usually takes the rest of the string.
                     query = action_args.strip()
                     if not query:
                         observation = "Error: Please provide a search query."
                     else:
                         observation = self.mapping_service.query_pdf_spec(session_id, query)

                elif action_name == "GET_FLAGGED_ROWS":
                     observation = self._tool_get_flagged_rows(session_id)

                elif action_name == "GET_NESTLE_FLAGS":
                     observation = self._tool_get_nestle_flags(session_id)
                
                yield json.dumps({"type": "thought", "content": f"\nObservation: {str(observation)[:300]}...\n"})
                
                # Append Observation to history for next turn
                obs_msg = f"OBSERVATION: {observation}"
                messages.append({"role": "user", "content": obs_msg})
                
            else:
                if not final_answer_text:
                    if buffer and buffer.strip():
                         # Fallback: If no ACTION and no explicit ANSWER, but we have text,
                         # treat the thought trace as the answer.
                         yield json.dumps({"type": "message", "content": buffer})
                    else:
                         yield json.dumps({"type": "message", "content": "I am not sure how to proceed."})
                break

        # Save History
        session["chat_history"].append({"role": "user", "content": user_query})
        session["chat_history"].append({"role": "assistant", "content": final_answer_text if final_answer_text else buffer})


    # Actual Tools
    def _tool_read_grid(self, session_id: str) -> str:
        session = self.mapping_service.sessions.get(session_id)
        if not session: return "Session lost."
        grid = session.get("grid", [])
        mappings = session.get("mappings", {})
        
        if not grid:
            return "Grid is empty."
            
        # Build Warning Lookup
        warnings = {}
        # 850 Structure: mappings[rec][field]['validation_warning']
        # 856 Structure: mappings['mappings'] list... (simpler)
        
        try:
            if "mappings" in mappings and isinstance(mappings["mappings"], list):
                # 856 logic (if needed later)
                pass 
            else:
                # 850 Logic: Flatten mappings
                for rec_id, fields in mappings.items():
                    for field_name, data in fields.items():
                        if isinstance(data, dict) and data.get("validation_warning"):
                             warnings[field_name] = data["validation_warning"]
        except:
            pass # Safe fallback
            
        # Format Top 15 rows with Explicit 0-based Index
        output = "GRID STATE (First 15 Rows):\n"
        
        # Print all rows including header with their actual list index
        for i, row in enumerate(grid[:15]):
            row_str = str(row)
            # Check for warning (Column 0 is usually Field Name in 850)
            if len(row) > 0:
                field_name = str(row[0])
                if field_name in warnings:
                    row_str += f"  <-- [FLAGGED: {warnings[field_name]}]"
                    
            output += f"[{i}] {row_str}\n"
            
        print(f"DEBUG_GRID_OUTPUT:\n{output}", flush=True)
        return output

    def _tool_get_flagged_rows(self, session_id: str) -> str:
        """Returns a list of all rows that have validation warnings (Red Flags)."""
        session = self.mapping_service.sessions.get(session_id)
        if not session: return "Session lost."
        grid = session.get("grid", [])
        mappings = session.get("mappings", {})
        
        if not grid: return "Grid is empty."
        
        flagged_items = []
        
        # 1. Build Lookup from Mappings
        warnings = {}
        try:
            if "mappings" in mappings and isinstance(mappings["mappings"], list):
                # 856 Logic
                pass
            else:
                # 850 Logic
                for rec_id, fields in mappings.items():
                    for field_name, data in fields.items():
                         if isinstance(data, dict) and data.get("validation_warning"):
                             warnings[field_name] = data["validation_warning"]
        except:
            return "Error parsing mappings for flags."

        # 2. Scan Grid
        for i, row in enumerate(grid):
            if len(row) > 0:
                field_name = str(row[0])
                if field_name in warnings:
                    flagged_items.append(f"Row {i}: {field_name} ({warnings[field_name]})")
        
        if not flagged_items:
            return "No red flagged cells found. The grid appears valid."
            
        return "RED FLAGGED CELLS:\n" + "\n".join(flagged_items)

    def _tool_update_row(self, session_id: str, row_idx: int, col_idx: int, verify_tag: str, value: str):
        session = self.mapping_service.sessions.get(session_id)
        if not session: return "Session lost."
        grid = session.get("grid")
        
        if not grid: return "Grid is empty."
        if row_idx < 0 or row_idx >= len(grid):
            return f"Error: Row index {row_idx} out of bounds."
            
        old_val = grid[row_idx][col_idx]
        
        # Sync to Mappings (Logic copied from api_server.py)
        session_type = session.get("type", "850")
        if session_type == "856":
            # For 856, Mapping is a list: session['mappings']['mappings']
            # row_idx includes header (0). So data index is row_idx - 1.
            data_idx = row_idx - 1
            
            if "mappings" in session and "mappings" in session["mappings"]:
                mapping_list = session["mappings"]["mappings"]
                if 0 <= data_idx < len(mapping_list):
                    item = mapping_list[data_idx]
                    # Verify element tag for safety
                    current_element = item.get('element', 'UNKNOWN')
                    
                    if verify_tag not in current_element:
                         return f"Error: SAFETY MISMATCH. You requested to update '{verify_tag}' at Row {row_idx}, but that row is actually '{current_element}'. Please CHECK READ_GRID output again and use the correct index."
                    
                    if col_idx == 3:
                         item["type"] = value
                    elif col_idx == 5:
                         item["hardcode"] = value
                    elif col_idx == 6:
                         item["logic"] = value
        
        # Update visible grid (if checks pass or skipped)
        grid[row_idx][col_idx] = value
        
        return f"Successfully updated Row {row_idx} ({verify_tag}), Col {col_idx}. Old: '{old_val}' -> New: '{value}'"

    def _tool_get_nestle_flags(self, session_id: str) -> str:
        """Returns all Nestle rows flagged for PDF value discrepancies (orange highlights)."""
        session = self.mapping_service.sessions.get(session_id)
        if not session:
            return "Session lost."

        # Check nestle session flags
        nestle_session = None
        if hasattr(self.mapping_service, 'nestle_service'):
            for sid, sess in self.mapping_service.nestle_service.sessions.items():
                if sid == session_id or session.get("nestle_session_id") == sid:
                    nestle_session = sess
                    break

        flags = (nestle_session or session).get("flags", {})
        grid = (nestle_session or session).get("grid", [])

        if not flags:
            return "No orange-flagged cells found. All standard mapping rules appear to cover the PDF-specified values."

        flagged_items = []
        for row_idx_str, flag_info in flags.items():
            row_idx = int(row_idx_str)
            reason = flag_info.get("reason", "")
            # Get context from grid
            if row_idx < len(grid):
                row = grid[row_idx]
                x12_elem = row[7] if len(row) > 7 else "?"
                mapping_rule = row[9] if len(row) > 9 else "?"
                flagged_items.append(
                    f"Row {row_idx}: {x12_elem} — Mapping Rule: \"{mapping_rule}\" — Flag: {reason}"
                )
            else:
                flagged_items.append(f"Row {row_idx}: {reason}")

        return f"ORANGE-FLAGGED CELLS ({len(flagged_items)} total):\n" + "\n".join(flagged_items)
