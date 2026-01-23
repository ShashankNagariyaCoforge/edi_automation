"""
Standard Field Mappings Module

Contains static/constant mappings for standard ERP fields that appear in every record type.
Loads mappings from input/standard_field_mappings.json if available.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional


# Standard field names (the green fields in the ERP definition)
# We use a set of stripped names for fast lookup
_STANDARD_FIELD_SET = {
    "TP Translator Code",
    "TP_Translator_Code",
    "Header Identifier (Location Identifier)",
    "Detail Line Identifier",
    "Sub-Detail Line Identifier",
    "Record Number",
    "Record Type Identifier",
    "Record Layout Qualifier"
}

# Map variations to the names used in the JSON
_FIELD_NAME_MAP = {
    "TP_Translator_Code": "TP Translator Code"
}

# Load mappings from JSON file
_MAPPINGS_FILE = Path(__file__).parent.parent / "input" / "standard_field_mappings.json"
_LOADED_MAPPINGS: Dict[str, Dict[str, str]] = {}
_NORMALIZED_KEYS: Dict[str, str] = {}  # Map normalized keys to original keys

def _load_mappings():
    """Load standard field mappings from JSON file."""
    global _LOADED_MAPPINGS, _NORMALIZED_KEYS
    if _MAPPINGS_FILE.exists():
        try:
            with open(_MAPPINGS_FILE, 'r') as f:
                _LOADED_MAPPINGS = json.load(f)
            # Create normalized key mapping (strip leading zeros)
            for key in _LOADED_MAPPINGS.keys():
                normalized = key.lstrip('0') or key
                _NORMALIZED_KEYS[normalized] = key
                _NORMALIZED_KEYS[key] = key  # Also map original to itself
        except Exception as e:
            print(f"Warning: Could not load standard mappings: {e}")
            _LOADED_MAPPINGS = {}

# Load on module import
_load_mappings()


def _find_record_mapping(record_type: str) -> Optional[Dict[str, str]]:
    """Find mapping for a record type, handling different key formats."""
    # Try direct match
    if record_type in _LOADED_MAPPINGS:
        return _LOADED_MAPPINGS[record_type]
    
    # Try normalized (without leading zeros)
    normalized = record_type.lstrip('0') or record_type
    if normalized in _NORMALIZED_KEYS:
        original_key = _NORMALIZED_KEYS[normalized]
        return _LOADED_MAPPINGS.get(original_key)
    
    # Try with leading zeros (e.g., "10" -> "0010")
    padded = record_type.zfill(4)
    if padded in _LOADED_MAPPINGS:
        return _LOADED_MAPPINGS[padded]
    
    return None


def get_standard_mapping(field_name: str, record_type: str) -> Optional[Dict[str, Any]]:
    """
    Get the standard mapping for a field based on record type.
    """
    field_name = field_name.strip()
    
    if field_name not in _STANDARD_FIELD_SET:
        return None
    
    # Use mapped name for JSON lookup if needed
    json_field_name = _FIELD_NAME_MAP.get(field_name, field_name)
    
    record_mappings = _find_record_mapping(record_type)
    if not record_mappings:
        return None
    
    if json_field_name not in record_mappings:
        return None
    
    value = record_mappings[json_field_name]
    
    # Determine if it's a segment reference or a constant
    if value and len(value) >= 3 and value[:2].isalpha() and any(c.isdigit() for c in value[2:]):
        return {
            "segment": value,
            "constant": None,
            "logic": f"Standard field - mapped to {value}"
        }
    elif value is not None:
        return {
            "segment": None,
            "constant": value,
            "logic": f"Standard field - constant value '{value}'"
        }
    else:
        return {
            "segment": None,
            "constant": "",
            "logic": "Standard field - empty value"
        }


def is_standard_field(field_name: str) -> bool:
    """Check if a field is a standard field."""
    return field_name.strip() in _STANDARD_FIELD_SET


def apply_standard_mappings(
    mappings: Dict[str, Dict[str, Any]], 
    record_type: str,
    field_names: list
) -> Dict[str, Dict[str, Any]]:
    """
    Apply standard mappings to fields.
    For known standard fields, ALWAYS use the standard mapping (override AI).
    """
    for field_name in field_names:
        standard = get_standard_mapping(field_name, record_type)
        if standard:
            mappings[field_name] = standard
    return mappings
