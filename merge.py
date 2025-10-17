"""
Assassin's Creed Cheat Table Merger
Merges two .CT files by combining their AssemblerScript entries with version-specific dynamic addresses.
"""
import sys
import re
import xml.etree.ElementTree as ET
import argparse
import logging
import os
from typing import Tuple, List, Dict
from common.utils import find_ct_files
from common.ct_file import get_assembler_scripts

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Constants for ID reset points in cleanALL.py
ID_RESET_BINDS = 100
ID_RESET_PARKOUR_MODE = 300
ID_RESET_EXTRA = 500
ID_RESET_VAULT_LANDING = 700

# Compile the dynamic pattern once at the module level.
# Matches patterns like:
#   ModuleName.exe+Offset
#   "ModuleName.exe"+Offset
#   [ModuleName.exe+Offset]
#   (ModuleName.exe+Offset)
#   ,ModuleName.exe+Offset
# Handles quoted and unquoted module names.
DYN_PATTERN = re.compile(
    r'('                                    # Start capturing group 1 (captures the whole desired string)
      r'(?:'                                # Start non-capturing group for OR between quoted/unquoted
          # Option 1: Quoted module name (allows spaces inside)
          r'"[^"]+\.exe"\+'
          r'|'                              # OR
          # Option 2: Unquoted module name
          # Exclude whitespace, quotes, plus, and common delimiters from the name part
          r'[^"+\s\[\](){},]+\.exe\+'
      r')'                                  # End non-capturing group
      r'[A-Fa-f0-9]+'                       # Hexadecimal offset
      r':?'                                 # Optional trailing colon
    r')',                                   # End capturing group 1
    re.IGNORECASE                           # Make .exe matching case-insensitive
)


def process_section(text: str, pattern: re.Pattern) -> Tuple[str, List[str]]:
    """
    Replace dynamic segments in text with '%s' and extract them.

    Args:
        text: The input text containing dynamic segments.
        pattern: A compiled regex pattern to identify dynamic parts.

    Returns:
        A tuple containing:
          - A template string with dynamic parts replaced by '%s'.
          - A list of extracted dynamic strings.
    """
    dyn_list: List[str] = []
    result: List[str] = []
    last_index = 0
    for m in pattern.finditer(text):
        start, end = m.start(), m.end()
        result.append(text[last_index:start])
        result.append("%s")
        dyn_list.append(m.group(0))
        last_index = end
    result.append(text[last_index:])
    template = "".join(result)
    return template, dyn_list

def build_lua_config_table(name: str, dyn_list_v1: List[str], dyn_list_v2: List[str]) -> Tuple[str, int]:
    """
    Build a Lua configuration table string for a section.
    'name' is used as the Lua variable name (e.g. config_enable).
    The table maps dynamic1, dynamic2, ... to the dynamic values.

    Args:
        name: The Lua variable name.
        dyn_list_v1: The list of dynamic values from the first script.
        dyn_list_v2: The list of dynamic values from the second script.

    Returns:
        A tuple containing:
          - The Lua configuration table string.
          - The number of dynamic entries.
    """
    if len(dyn_list_v1) != len(dyn_list_v2):
        raise ValueError(f"Dynamic value count mismatch for {name}: {len(dyn_list_v1)} vs {len(dyn_list_v2)}")
    n = len(dyn_list_v1)

    def build_version_table(values: List[str]) -> str:
        lines = []
        for i, val in enumerate(values, start=1):
            # Escape backslashes first, then quotes
            safe_val = val.replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'        dynamic{i} = "{safe_val}"')
        return "{\n" + ",\n".join(lines) + "\n    }"

    table = (
f"""local {name} = {{
    [1] = {build_version_table(dyn_list_v1)},
    [2] = {build_version_table(dyn_list_v2)}
}}"""
    )
    return table, n

def split_asm_sections(text: str) -> Tuple[str, str]:
    """
    Split an AssemblerScript text into ENABLE and DISABLE parts.
    Removes a leading [ENABLE] header if present.

    Args:
        text: The full AssemblerScript text.

    Returns:
        A tuple containing the ENABLE and DISABLE sections.
    """
    text = text.lstrip()
    if text.startswith("[ENABLE]"):
        text = text[len("[ENABLE]"):].lstrip()
    parts = re.split(r"(\[DISABLE\])", text, maxsplit=1, flags=re.IGNORECASE) # Case-insensitive split
    enable = parts[0].strip()
    disable = ""
    if len(parts) > 1:
        disable = parts[2].strip() if len(parts) > 2 else "" # Get text after [DISABLE]

    return enable, disable

def build_script_part(template: str, dyn_count: int, script_var: str, addr_prefix: str) -> str:
    """
    Build the Lua script part using a given template and dynamic count.

    Args:
        template: The template with '%s' placeholders.
        dyn_count: The number of dynamic values.
        script_var: The Lua variable name for the script (e.g. 'enableScript').
        addr_prefix: The prefix for dynamic addresses (e.g. 'addrE' or 'addrD').

    Returns:
        The formatted Lua script part.
    """
    # Escape any existing percent signs in the template that aren't placeholders
    # Needs careful handling to avoid double-escaping our intended %s
    # A simple approach: temporarily replace %s with a unique marker, escape %, then restore %s
    placeholder = "__TEMP_PLACEHOLDER__"
    template_escaped = template.replace('%s', placeholder).replace('%', '%%').replace(placeholder, '%s')

    if dyn_count > 0:
        dyn_keys = ", ".join([f"{addr_prefix}.dynamic{i}" for i in range(1, dyn_count + 1)])
        # Use standard Lua string literal with explicit escapes for safety inside format
        lua_template_str = f"[[\\n{template_escaped}\\n]]"
        # Note: string.format requires careful escaping if template itself contains format specifiers
        # Using raw string literals [==[ ... ]==] can simplify things if template is complex
        # but requires ensuring the template doesn't contain the closing ]==] sequence.
        # Let's try the [==[ approach for robustness
        return f"""local {script_var} = string.format([==[\n{template_escaped}\n]==], {dyn_keys})"""

    else:
        # If no dynamic parts, just use the raw string literal
         return f"""local {script_var} = [==[\n{template}\n]==]"""


def merge_asm_scripts(asm1: str, asm2: str) -> str:
    """
    Merge two AssemblerScript texts by combining their ENABLE and DISABLE sections.

    Args:
        asm1: The first AssemblerScript text.
        asm2: The second AssemblerScript text.

    Returns:
        The merged AssemblerScript text.
    """
    # Split each script into its [ENABLE] and [DISABLE] parts.
    enable1, disable1 = split_asm_sections(asm1)
    enable2, disable2 = split_asm_sections(asm2)

    # Process ENABLE sections.
    enable_template1, dyn_enable_v1 = process_section(enable1, DYN_PATTERN)
    enable_template2, dyn_enable_v2 = process_section(enable2, DYN_PATTERN)

    # Process DISABLE sections.
    disable_template1, dyn_disable_v1 = process_section(disable1, DYN_PATTERN)
    disable_template2, dyn_disable_v2 = process_section(disable2, DYN_PATTERN)

    # Verify dynamic count matches.
    if len(dyn_enable_v1) != len(dyn_enable_v2):
        raise ValueError(f"Mismatch in dynamic values count in ENABLE sections ({len(dyn_enable_v1)} vs {len(dyn_enable_v2)})")
    if len(dyn_disable_v1) != len(dyn_disable_v2):
        raise ValueError(f"Mismatch in dynamic values count in DISABLE sections ({len(dyn_disable_v1)} vs {len(dyn_disable_v2)})")

    lua_config_enable, num_enable = build_lua_config_table("config_enable", dyn_enable_v1, dyn_enable_v2)
    lua_config_disable, num_disable = build_lua_config_table("config_disable", dyn_disable_v1, dyn_disable_v2)

    # Build script parts using the helper function.
    # Using the template from the *first* script (template1) for both enable/disable parts.
    # This assumes the structure is the same, only dynamic values differ.
    enable_part = build_script_part(enable_template1, num_enable, "enableScript", "addrE")
    disable_part = build_script_part(disable_template1, num_disable, "disableScript", "addrD")

    # Build the final merged script text.
    # Ensure disableInfo handling is robust even if disable script is empty
    disable_logic = """
if disableInfo and disableInfo.info then
    autoAssemble(disableScript, disableInfo.info)
else
    autoAssemble(disableScript) -- Might do nothing if script is empty, that's okay
end
disableInfo = nil""" if disable_template1 or num_disable > 0 else "disableInfo = nil -- No disable script"

    merged_script = f"""[ENABLE]
{{$lua}}
if syntaxcheck then return end

{lua_config_enable}

local addrE = config_enable[version]
if not addrE then error("Could not determine addresses for the current game version (" .. tostring(version) .. ")") end

{enable_part}

local success, info = autoAssemble(enableScript)
if not success then
    error("Assembly failed: " .. tostring(info))
end

-- Save disable info for use in the disable section
disableInfo = {{ info = info }} -- Store assembly info (registers, allocations)
{{$asm}}

[DISABLE]
{{$lua}}
if syntaxcheck then return end

{lua_config_disable}

local addrD = config_disable[version]
if not addrD then error("Could not determine disable addresses for the current game version (" .. tostring(version) .. ")") end

{disable_part}

{disable_logic}
{{$asm}}
"""

    return merged_script



def merge_cheat_entries(asm_map1: Dict[str, ET.Element], asm_map2: Dict[str, ET.Element]) -> int:
    """
    For every cheat entry in the first mapping that also exists in the second mapping,
    merge the AssemblerScript texts.

    Args:
        asm_map1: Dictionary mapping cheat IDs to AssemblerScript elements from the first CT file.
        asm_map2: Dictionary mapping cheat IDs to AssemblerScript elements from the second CT file.

    Returns:
        The number of successfully merged entries.
    """
    merged_count = 0
    skipped_count = 0
    error_count = 0

    for cheat_id, asm_elem1 in asm_map1.items():
        if cheat_id in asm_map2:
            asm_text1 = asm_elem1.text or "" # Use empty string if text is None
            asm_text2 = asm_map2[cheat_id].text or "" # Use empty string if text is None

            # Only attempt merge if both scripts are non-empty or structure needs merging anyway
            # Simplification: Always try to merge, merge_asm_scripts should handle empty inputs gracefully if needed
            try:
                merged_text = merge_asm_scripts(asm_text1, asm_text2)
                asm_elem1.text = merged_text
                logging.debug("Merged cheat entry ID %s", cheat_id) # Debug level for successful merges
                merged_count += 1
            except ValueError as ve: # Catch specific expected errors like count mismatch
                logging.error("Error merging cheat entry ID %s: %s", cheat_id, ve)
                error_count += 1
            except Exception as e:
                logging.error("Unexpected error merging cheat entry ID %s: %s", cheat_id, e, exc_info=True) # Log traceback for unexpected errors
                error_count += 1
        else:
            logging.warning("Cheat entry ID %s not found in second CT file; skipping merge.", cheat_id)
            skipped_count += 1

    logging.info(f"Merge process summary: {merged_count} merged, {error_count} errors, {skipped_count} skipped (not in second file).")
    return merged_count



def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments using argparse.

    Returns:
        Parsed arguments namespace containing input_folder.
    """
    parser = argparse.ArgumentParser(
        description="Merge AssemblerScript entries from two CT files found within a specified folder."
    )
    parser.add_argument("input_folder", help="Path to the folder containing exactly two CT files")
    # Optional: Add verbosity flag
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Enable verbose debug logging"
    )
    return parser.parse_args()

def main() -> None:
    args = parse_arguments()
    input_folder = args.input_folder

    # Adjust logging level if verbose flag is set
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    if not os.path.isdir(input_folder):
        logging.error("Input path is not a valid directory: %s", input_folder)
        sys.exit(1)

    # Additional validation for directory accessibility
    if not os.access(input_folder, os.R_OK):
        logging.error("Directory is not readable: %s", input_folder)
        sys.exit(1)

    logging.info(f"Scanning folder for CT files: {input_folder}")
    ct_files = find_ct_files(input_folder)

    if len(ct_files) != 2:
        logging.error(f"Expected exactly 2 CT files in '{input_folder}', but found {len(ct_files)}.")
        if ct_files:
            logging.error("Found files: %s", ", ".join([os.path.basename(f) for f in ct_files]))
        sys.exit(1)

    first_ct, second_ct = ct_files[0], ct_files[1]

    # Validate both CT files are accessible
    for ct_file in [first_ct, second_ct]:
        if not os.path.isfile(ct_file):
            logging.error("CT file does not exist: %s", ct_file)
            sys.exit(1)
        if not os.access(ct_file, os.R_OK):
            logging.error("CT file is not readable: %s", ct_file)
            sys.exit(1)

    # Create output path: same directory as script, inside a "Merged" folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    merged_dir = os.path.join(script_dir, "Merged")
    os.makedirs(merged_dir, exist_ok=True)

    # Build output filename based on base input
    base_name = os.path.splitext(os.path.basename(first_ct))[0]
    output_filename = f"{base_name}_Merged.CT"
    output_ct = os.path.join(merged_dir, output_filename)

    logging.info(f"Using '{os.path.basename(first_ct)}' as base (version 1).")
    logging.info(f"Using '{os.path.basename(second_ct)}' for version 2 data.")
    logging.info(f"Output will be saved as '{os.path.basename(output_ct)}'.")


    try:
        tree1 = ET.parse(first_ct, parser=ET.XMLParser(encoding='utf-8'))
        logging.debug("Successfully parsed %s", first_ct)
    except ET.ParseError as pe:
        logging.error("Failed to parse %s: %s", first_ct, pe)
        sys.exit(1)
    except UnicodeDecodeError as e:
        logging.error("Failed to decode %s: %s", first_ct, e)
        sys.exit(1)
    except IOError as e:
        logging.error("Failed to read %s: %s", first_ct, e)
        sys.exit(1)
    except Exception as e:
        logging.error("An unexpected error occurred while parsing %s: %s", first_ct, e, exc_info=True)
        sys.exit(1)


    try:
        tree2 = ET.parse(second_ct, parser=ET.XMLParser(encoding='utf-8'))
        logging.debug("Successfully parsed %s", second_ct)
    except ET.ParseError as pe:
        logging.error("Failed to parse %s: %s", second_ct, pe)
        sys.exit(1)
    except UnicodeDecodeError as e:
        logging.error("Failed to decode %s: %s", second_ct, e)
        sys.exit(1)
    except IOError as e:
        logging.error("Failed to read %s: %s", second_ct, e)
        sys.exit(1)
    except Exception as e:
        logging.error("An unexpected error occurred while parsing %s: %s", second_ct, e, exc_info=True)
        sys.exit(1)

    asm_map1 = get_assembler_scripts(tree1)
    asm_map2 = get_assembler_scripts(tree2)

    logging.info(f"Found {len(asm_map1)} script entries in {os.path.basename(first_ct)}.")
    logging.info(f"Found {len(asm_map2)} script entries in {os.path.basename(second_ct)}.")


    merged_count = merge_cheat_entries(asm_map1, asm_map2)

    if merged_count > 0 or len(asm_map1) > 0 : # Write output if merges happened or if base file had entries
        try:
            # Use ET.indent for pretty printing if available (Python 3.9+)
            if hasattr(ET, 'indent'):
                ET.indent(tree1.getroot())

            # Ensure output directory exists and is writable
            if not os.access(merged_dir, os.W_OK):
                logging.error("Output directory is not writable: %s", merged_dir)
                sys.exit(1)

            tree1.write(output_ct, encoding="utf-8", xml_declaration=True)
            logging.info("Merged CT file created: %s", output_ct)
        except IOError as e:
            logging.error("Failed to write merged CT file %s: %s", output_ct, e)
            sys.exit(1)
        except Exception as e:
            logging.error("Failed to write merged CT file %s: %s", output_ct, e, exc_info=True)
            sys.exit(1)
    else:
        logging.warning("No mergeable entries found or processed. Output file not written.")


if __name__ == "__main__":
    main()