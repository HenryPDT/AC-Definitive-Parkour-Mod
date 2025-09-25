import sys
import os
import re
from common.utils import find_ct_files

# Regular expression to find addresses in the format ["']Process.exe+hex or Process.exe+hex
address_re = re.compile(
    r'''
    (["']?)             # Group 1: Optional opening quote
    (                   # Group 2: Process name capture starts
        (?:(?=(\\\1))   #   Lookahead for the opening quote if present
            (?:.*?\.exe) #   Process name with .exe
        |               #   OR for unquoted process names
            ([^+]*?\.exe) #   Process name without quotes
        )               # Close the non-capturing group for alternatives
    )                   # Close Group 2
    \1                  # Match the closing quote (if any)
    \+                  # Plus sign
    ([0-9A-Fa-f]+)      # Group 3: Hex address part
    ''',
    re.IGNORECASE | re.VERBOSE
)

def find_addresses(line):
    addresses = []
    for match in address_re.finditer(line):
        process_part = match.group(2)
        hex_part = match.group(5).upper()  # Normalize hex to uppercase

        # Extract only the exe file name from the process part using a regex search.
        exe_match = re.search(r'(AssassinsCreed_Dx(?:9|10)\.exe)', process_part, re.IGNORECASE)
        if exe_match:
            process_name = exe_match.group(1)
        else:
            # Fallback: if the expected pattern isn't found, remove any leading/trailing characters.
            process_name = process_part.split('.exe')[0] + '.exe'
        
        # Normalize both DX9 and DX10 versions to a common name.
        if process_name.lower().startswith("assassinscreed_dx"):
            process_name = "AssassinsCreed.exe"

        addresses.append((process_name, hex_part))
    return addresses

def verify_files(folder_path):
    ct_files = find_ct_files(folder_path)
    if len(ct_files) != 2:
        return [f"Error: Folder must contain exactly two .CT files, but found {len(ct_files)}."]

    file1, file2 = ct_files[0], ct_files[1]
    with open(file1, 'r') as f1, open(file2, 'r') as f2:
        lines1 = f1.read().splitlines()
        lines2 = f2.read().splitlines()

    errors = []

    if len(lines1) != len(lines2):
        errors.append(f"Error: Files have different number of lines ({len(lines1)} vs {len(lines2)})")

    for line_num, (line1, line2) in enumerate(zip(lines1, lines2), 1):
        # Check for db lines
        if line1.strip().lower().startswith('db') and line2.strip().lower().startswith('db'):
            continue
        if line1.strip().lower().startswith('db') or line2.strip().lower().startswith('db'):
            errors.append(f"Error line {line_num}: One line starts with 'db' and the other does not.")
            continue

        addresses1 = find_addresses(line1)
        addresses2 = find_addresses(line2)

        if len(addresses1) != len(addresses2):
            errors.append(f"Error line {line_num}: Different number of addresses ({len(addresses1)} vs {len(addresses2)})")

        # Replace addresses to check line structure
        modified_line1 = address_re.sub('{ADDR}', line1)
        modified_line2 = address_re.sub('{ADDR}', line2)
        if modified_line1 != modified_line2:
            errors.append(f"Error line {line_num}: Lines differ outside of addresses.")
            errors.append(f"  Line 1: {modified_line1}")
            errors.append(f"  Line 2: {modified_line2}")

        # Check each address pair
        for (proc1, hex1), (proc2, hex2) in zip(addresses1, addresses2):
            if proc1 != proc2:
                errors.append(f"Error line {line_num}: Process names differ '{proc1}' vs '{proc2}'")

            # Check if the line contains addresses in square brackets
            is_bracket_address = '[' in line1 and ']' in line1 and '[' in line2 and ']' in line2

            if is_bracket_address:
                # Lenient check for addresses in brackets: must be different.
                if hex1 == hex2:
                    errors.append(f"Error line {line_num}: Addresses are identical '{hex1}'")
            else:
                # Strict check for other addresses (e.g., jumps)
                if hex1 == hex2:
                    errors.append(f"Error line {line_num}: Addresses are identical '{hex1}'")
                
                if len(hex1) > 0 and len(hex2) > 0 and hex1[-1] != hex2[-1]:
                    errors.append(f"Error line {line_num}: Last hex character must be the same for jumps, but differs '{hex1}' vs '{hex2}'")
                    errors.append(f"  Line 1: {line1}")
                    errors.append(f"  Line 2: {line2}")

            # rest1 = hex1[:-1]
            # rest2 = hex2[:-1]
            # if rest1 == rest2:
            #     errors.append(f"Error line {line_num}: Addresses differ only in the last character '{hex1}' vs '{hex2}'")

    if not errors:
        errors.append("Verification passed. All checks completed successfully.")
    return errors

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify.py <folder_path>")
        sys.exit(1)
    folder_path = sys.argv[1]
    if not os.path.isdir(folder_path):
        print(f"Error: {folder_path} is not a valid directory.")
        sys.exit(1)
    results = verify_files(folder_path)
    for result in results:
        print(result)
    sys.exit(0 if "Verification passed. All checks completed successfully." in results else 1)