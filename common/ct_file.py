import xml.etree.ElementTree as ET
from typing import Dict

def get_assembler_scripts(tree: ET.ElementTree) -> Dict[str, ET.Element]:
    """
    Build a dictionary of cheat entries (keyed by ID) that have an AssemblerScript.

    Args:
        tree: An XML ElementTree representing the CT file.

    Returns:
        A dictionary mapping cheat entry IDs to their <AssemblerScript> element.
    """
    mapping: Dict[str, ET.Element] = {}
    for cheat in tree.iter('CheatEntry'):
        id_elem = cheat.find('ID')
        if id_elem is not None and id_elem.text:
            cheat_id = id_elem.text.strip()
            asm_elem = cheat.find('AssemblerScript')
            # Ensure the element exists and has text content (even if empty)
            if asm_elem is not None and asm_elem.text is not None:
                mapping[cheat_id] = asm_elem
            elif asm_elem is not None and asm_elem.text is None:
                 # Handle cases where <AssemblerScript/> exists but is empty
                 asm_elem.text = "" # Assign empty string to allow processing
                 mapping[cheat_id] = asm_elem

    return mapping