#!/usr/bin/env python3
import sys
import re
import xml.etree.ElementTree as ET

# --- Helper functions from your original script ---

def process_section(text, pattern):
    """
    Given a section text and a compiled regex pattern,
    returns a tuple (template, dyn_list) where:
      - template is the text with each match replaced by '%s'
      - dyn_list is a list of the matched dynamic strings in order
    """
    dyn_list = []
    result = []
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

def build_lua_config_table(name, dyn_list_v1, dyn_list_v2):
    """
    Build a Lua configuration table string for a section.
    'name' is used as the Lua variable name (e.g. config_enable).
    The table maps dynamic1, dynamic2, ... to the dynamic values.
    """
    if len(dyn_list_v1) != len(dyn_list_v2):
        raise ValueError(f"Dynamic value count mismatch for {name}: {len(dyn_list_v1)} vs {len(dyn_list_v2)}")
    n = len(dyn_list_v1)
    def build_version_table(values):
        lines = []
        for i, val in enumerate(values, start=1):
            safe_val = val.replace('"', '\\"')
            lines.append(f'        dynamic{i} = "{safe_val}"')
        return "{\n" + ",\n".join(lines) + "\n    }"
    table = (
f"""local {name} = {{
    [1] = {build_version_table(dyn_list_v1)},
    [2] = {build_version_table(dyn_list_v2)}
}}"""
    )
    return table, n

# --- New helper: split an AssemblerScript text into ENABLE and DISABLE parts ---
def split_asm_sections(text):
    # Remove a leading [ENABLE] header if present
    text = text.lstrip()
    if text.startswith("[ENABLE]"):
        text = text[len("[ENABLE]"):].lstrip()
    parts = text.split("[DISABLE]")
    enable = parts[0].strip()
    disable = parts[1].strip() if len(parts) > 1 else ""
    return enable, disable

# --- Merge two AssemblerScript texts ---
def merge_asm_scripts(asm1, asm2):
    # Split each script into its [ENABLE] and [DISABLE] parts
    enable1, disable1 = split_asm_sections(asm1)
    enable2, disable2 = split_asm_sections(asm2)
    
    # Define the dynamic pattern (addresses to be merged)
    dyn_pattern = re.compile(
        r'((?:"AssassinsCreedIIGame\.exe"\+|AssassinsCreedIIGame\.exe\+)[A-Fa-f0-9]+:?)',
        re.IGNORECASE
    )
    
    # Process ENABLE sections
    enable_template1, dyn_enable_v1 = process_section(enable1, dyn_pattern)
    enable_template2, dyn_enable_v2 = process_section(enable2, dyn_pattern)
    
    # Process DISABLE sections
    disable_template1, dyn_disable_v1 = process_section(disable1, dyn_pattern)
    disable_template2, dyn_disable_v2 = process_section(disable2, dyn_pattern)
    
    # Verify dynamic count matches
    if len(dyn_enable_v1) != len(dyn_enable_v2):
        raise ValueError("Mismatch in dynamic values count in ENABLE sections")
    if len(dyn_disable_v1) != len(dyn_disable_v2):
        raise ValueError("Mismatch in dynamic values count in DISABLE sections")
    
    lua_config_enable, num_enable = build_lua_config_table("config_enable", dyn_enable_v1, dyn_enable_v2)
    lua_config_disable, num_disable = build_lua_config_table("config_disable", dyn_disable_v1, dyn_disable_v2)
    
    # Build dynamic key lists if needed
    if num_enable > 0:
        dyn_keys_enable = ", ".join([f"addrE.dynamic{i}" for i in range(1, num_enable+1)])
        enable_part = f"""local enableScript = string.format([==[
{enable_template1}
]==], {dyn_keys_enable})"""
    else:
        enable_part = f"""local enableScript = [==[
{enable_template1}
]==]"""
    
    if num_disable > 0:
        dyn_keys_disable = ", ".join([f"addrD.dynamic{i}" for i in range(1, num_disable+1)])
        disable_part = f"""local disableScript = string.format([==[
{disable_template1}
]==], {dyn_keys_disable})"""
    else:
        disable_part = f"""local disableScript = [==[
{disable_template1}
]==]"""
    
    # Build the final merged script text
    merged_script = f"""[ENABLE]
{{$lua}}
if syntaxcheck then return end

{lua_config_enable}

local addrE = config_enable[version]

{enable_part}

local success, info = autoAssemble(enableScript)
if not success then
    error("Assembly failed: " .. tostring(info))
end

-- Save disable info for use in the disable section
disableInfo = {{ info = info }}
{{$asm}}

[DISABLE]
{{$lua}}
if syntaxcheck then return end

{lua_config_disable}

local addrD = config_disable[version]

{disable_part}

if disableInfo then
    autoAssemble(disableScript, disableInfo.info)
else
    autoAssemble(disableScript)
end
disableInfo = nil
{{$asm}}"""
    
    return merged_script

# --- XML helper: Build a dictionary of cheat entries (keyed by ID) that have an AssemblerScript ---
def get_assembler_scripts(tree):
    mapping = {}
    for cheat in tree.iter('CheatEntry'):
        id_elem = cheat.find('ID')
        if id_elem is not None:
            cheat_id = id_elem.text.strip()
            asm_elem = cheat.find('AssemblerScript')
            if asm_elem is not None and asm_elem.text is not None:
                mapping[cheat_id] = asm_elem
    return mapping

# --- Main processing ---
def main():
    if len(sys.argv) != 4:
        print("Usage: python merge_ct_dynamic.py <first.ct> <second.ct> <output.ct>")
        sys.exit(1)
    
    first_ct, second_ct, output_ct = sys.argv[1], sys.argv[2], sys.argv[3]
    
    # Parse both CT files
    tree1 = ET.parse(first_ct)
    tree2 = ET.parse(second_ct)
    
    # Create dictionaries mapping cheat entry IDs to their <AssemblerScript> element
    asm_map1 = get_assembler_scripts(tree1)
    asm_map2 = get_assembler_scripts(tree2)
    
    # For every cheat entry in file1 that also exists in file2, merge the AssemblerScript texts.
    for cheat_id, asm_elem1 in asm_map1.items():
        if cheat_id in asm_map2:
            asm_text1 = asm_elem1.text
            asm_text2 = asm_map2[cheat_id].text
            try:
                merged_text = merge_asm_scripts(asm_text1, asm_text2)
                asm_elem1.text = merged_text
                print(f"Merged cheat entry ID {cheat_id}")
            except Exception as e:
                print(f"Error merging cheat entry ID {cheat_id}: {e}")
        else:
            print(f"Cheat entry ID {cheat_id} not found in second CT file; skipping.")
    
    # Write the updated tree1 to the output file.
    tree1.write(output_ct, encoding="utf-8", xml_declaration=True)
    print("Merged CT file created:", output_ct)

if __name__ == "__main__":
    main()
