"""
AI client module for LLM integration via company portal.
Supports different authentication methods and includes JSON repair logic.
"""
import json
import re
import time
import httpx
from typing import Dict, List, Any, Optional
from .logger import get_logger


class AIClient:
    """AI client using OpenAI-compatible API with custom base URL and auth."""
    
    def __init__(self, base_url: str, api_key: str, model: str, 
                 timeout: int = 120, max_retries: int = 3,
                 auth_type: str = "bearer", auth_header_name: Optional[str] = None):
        """
        Initialize AI client with company LLM portal.
        
        Args:
            base_url: Company LLM portal base URL
            api_key: API key from company portal
            model: Model name to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            auth_type: Authentication type - "bearer", "x-api-key", "basic", or "custom"
            auth_header_name: Custom header name when auth_type is "custom"
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.auth_type = auth_type
        self.auth_header_name = auth_header_name
        self.logger = get_logger()
        
        self._init_client()
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers based on auth_type."""
        if self.auth_type == "bearer":
            return {"Authorization": f"Bearer {self.api_key}"}
        elif self.auth_type == "x-api-key":
            return {"x-api-key": self.api_key}
        elif self.auth_type == "basic":
            return {"Authorization": f"Basic {self.api_key}"}
        elif self.auth_type == "custom" and self.auth_header_name:
            return {self.auth_header_name: self.api_key}
        else:
            return {"Authorization": f"Bearer {self.api_key}"}
    
    def _init_client(self):
        """Initialize the HTTP client."""
        self.headers = {
            "Content-Type": "application/json",
            **self._get_auth_headers()
        }
        self.client = httpx.Client(timeout=self.timeout)
        self.logger.info(f"Initialized LLM client: {self.base_url}, model: {self.model}, auth: {self.auth_type}")
    
    def generate_mapping(self, edi_summary: str, record_num: str, 
                         fields: List[str]) -> Dict[str, Dict[str, Any]]:
        """Generate EDI mapping for a specific record's fields."""
        prompt = self._build_prompt(edi_summary, record_num, fields)
        
        for attempt in range(self.max_retries):
            try:
                response = self._call_api(prompt)
                result = self._parse_response(response, fields)
                return result
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                else:
                    # On final attempt, try to repair the JSON
                    try:
                        repaired = self._repair_json(response, fields)
                        if repaired:
                            return repaired
                    except:
                        pass
                    raise
            except Exception as e:
                self.logger.error(f"API error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                else:
                    raise
        
        return {}
    
    def _build_prompt(self, edi_summary: str, record_num: str, fields: List[str]) -> str:
        """Build the prompt for the AI model."""
        fields_list = "\n".join([f"  - {field}" for field in fields])
        
        prompt = f"""You are an EDI mapping expert. 
Your job is to identify which EDI segment and element contains the data for a given ERP field.

## AVAILABLE EDI DATA (from Sample File):
{edi_summary}

## TASK:
Map the following ERP fields (Record Type: {record_num}) to the EDI segments/elements found in the sample data.

Fields to Map:
{fields_list}

## INSTRUCTIONS:
1. Review the Field Name and Record Type context.
2. Search the "EDI Structure Summary" for the corresponding data.
3. If found, specify the Segment and Element (e.g. "BEG03").
4. If the field is a constant (e.g. "ED", "Y"), specify it in the "constant" field.
5. Provide logic/comments for complex mappings or if the field requires conditional logic (Column J).
6. If the field is NOT found in the sample but you know the standard mapping (e.g. typical 850 structure), you may suggest it, but note "Not in sample" in the logic.
7. If uncertain, map as "NEEDS_REVIEW".

## OUTPUT FORMAT:
Respond ONLY with a JSON object.
The keys must be the exact field names provided.
The values must be objects with: "segment", "constant", "logic".

Example Entry:
"PO_NUMBER": {{
  "segment": "BEG03",
  "constant": null,
  "logic": "Direct mapping from BEG segment element 03"
}}

Example Constant:
"RECORD_TYPE": {{
  "segment": null,
  "constant": "1000",
  "logic": "Constant value for Header record"
}}

IMPORTANT: 
- Respond with JSON only. 
- Ensure all requested fields are in the JSON.
"""
        return prompt
    
    def get_completion(self, prompt: str, system_prompt: str = "You are an EDI mapping expert. Always respond with valid JSON only. Keep responses concise.") -> str:
        """Generic method to get completion from LLM."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096
        }
        
        url = f"{self.base_url}/chat/completions"
        
        response = self.client.post(url, json=payload, headers=self.headers)
        
        if response.status_code != 200:
            raise Exception(f"Error code: {response.status_code} - {response.text}")
        
        data = response.json()
        
        # Handle different response formats
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        elif "content" in data:
            return data["content"]
        elif "response" in data:
            return data["response"]
        else:
            return json.dumps(data)

    def _call_api(self, prompt: str) -> str:
        """Call the LLM API and return the response text."""
        return self.get_completion(prompt)
    
    def _repair_json(self, response: str, fields: List[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        """Attempt to repair truncated or malformed JSON."""
        self.logger.debug("Attempting to repair JSON response")
        
        response = response.strip()
        
        # Remove markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            # Filter out the first line if it is ```json or just ```
            # and the last line if it is ```
            clean_lines = []
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)
        
        # Try to find valid JSON object boundaries
        start = response.find("{")
        if start != -1:
            response = response[start:]
        
        # Count braces to find where JSON might be truncated
        brace_count = 0
        last_complete_pos = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(response):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_complete_pos = i + 1
                    # Don't break immediately, find the LAST valid closing brace if multiple objects? 
                    # Actually for a single root object, break here.
                    break
        
        if last_complete_pos > 0:
            response = response[:last_complete_pos]
        else:
            # Try to close the JSON properly
            response = response.rstrip(',\n\t ')
            while brace_count > 0:
                response += "}"
                brace_count -= 1
        
        try:
            result = json.loads(response)
            self.logger.info("Successfully repaired JSON response")
            return result
        except json.JSONDecodeError:
            # Create empty mappings for all fields if repair fails
            self.logger.warning("Could not repair JSON, returning empty mappings")
            return {field: {"segment": "PARSE_ERROR", "constant": None, "logic": "Failed to parse LLM response"} for field in fields}
    
    def _parse_response(self, response: str, fields: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse the JSON response from the AI."""
        response = response.strip()
        
        # Extract JSON block if hidden in text
        try:
            # 1. Try finding code block first
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.rfind("```") # Use rfind to get the last one
                if end != -1:
                    response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.rfind("```")
                if end != -1:
                    response = response[start:end].strip()
            
            # Simple cleanup if not in code block but includes text
            if not response.startswith("{") or not response.endswith("}"):
                 start = response.find("{")
                 end = response.rfind("}")
                 if start != -1 and end != -1:
                     response = response[start:end+1]

            result = json.loads(response)
        except json.JSONDecodeError:
             raise
        
        # Validate that we have mappings for the requested fields
        missing_fields = [f for f in fields if f not in result]
        if missing_fields:
            self.logger.warning(f"Missing mappings for fields: {missing_fields}")
            # Add empty entries for missing fields
            for field in missing_fields:
                result[field] = {"segment": "NOT_FOUND", "constant": None, "logic": "Not found in LLM response"}
        
        return result
    
    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, 'client'):
            self.client.close()
