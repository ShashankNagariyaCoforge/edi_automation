"""
EDI Parser Module
Parses EDI X12 files and generates summaries for AI context.
"""
from typing import Dict, List, Any

def parse_edi_file(edi_text: str) -> Dict[str, List[List[str]]]:
    """
    Parse EDI text into a structured dictionary.
    
    Args:
        edi_text: Raw EDI file content
        
    Returns:
        Dictionary where keys are segment IDs (e.g., 'BEG', 'N1') and 
        values are lists of segment occurrences, where each occurrence
        is a list of elements.
        {
            'BEG': [['00', 'NE', 'PO123', ...]], 
            'N1': [['ST', 'Name', ...], ['BT', 'Name', ...]]
        }
    """
    segments = {}
    
    # Clean and split by segment terminator (~)
    # Note: Real EDI might use different terminators, but ~ is standard for X12
    # We could make this more robust by auto-detecting headers if needed
    lines = edi_text.strip().split('~')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Split by element separator (*)
        parts = line.split('*')
        
        if not parts:
            continue
            
        seg_id = parts[0].strip()
        elements = parts[1:] if len(parts) > 1 else []
        
        # Clean elements (remove potential whitespace if it's not data)
        # But be careful not to remove spaces inside data
        # EDI elements usually don't have surrounding whitespace unless it is part of the data
        
        if seg_id not in segments:
            segments[seg_id] = []
        segments[seg_id].append(elements)
    
    return segments


def create_edi_summary(edi_parsed: Dict[str, List[List[str]]]) -> str:
    """
    Create a human-readable summary of EDI content for AI context.
    
    Args:
        edi_parsed: Dictionary returned by parse_edi_file
        
    Returns:
        Structured string representation for the LLM
    """
    summary = "EDI Structure Summary:\n\n"
    
    # Process segments in order of typical appearance or just sort keys?
    # Keeping them in the order they were inserted would be best if python dicts preserved order (3.7+)
    # But since we built the dict by iterating, the keys insertion order depends on first appearance.
    
    for seg_id, occurrences in edi_parsed.items():
        summary += f"Segment: {seg_id} (Occurrences: {len(occurrences)})\n"
        for idx, elements in enumerate(occurrences):
            summary += f"  Occurrence {idx + 1}:\n"
            for i, elem in enumerate(elements, 1):
                # Only show non-empty elements to save context window
                if elem and elem.strip():
                    summary += f"    {seg_id}{i:02d}: {elem}\n"
        summary += "\n"
    
    return summary
