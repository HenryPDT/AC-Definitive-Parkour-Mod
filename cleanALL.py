import re
import os

# Function to determine the renumbering range
def renumber_id(match):
    global id_counter
    new_id = f"<ID>{id_counter}</ID>"
    id_counter += 1
    return new_id

# Prompt the user for the directory path
directory = input("Enter the path to the directory: ").strip()

# Validate if the directory exists
if not os.path.isdir(directory):
    print("Error: The specified directory does not exist.")
    exit(1)

# Walk through the directory and its subdirectories
for root, _, files in os.walk(directory):
    for file in files:
        # Process only .CT files
        if file.endswith(".CT"):
            input_file = os.path.join(root, file)

            # Initialize renumbering variables for each file
            id_counter = 0  # Reset renumbering at the start of a new file
            binds_found = False
            parkour_mode_found = False
            extra_found = False
            vault_landing_found = False

            # Read the file
            with open(input_file, 'r') as f:
                lines = f.readlines()

            processed_lines = []
            inside_userdefined_symbols = False  # Track if inside <UserdefinedSymbols> section
            inside_cheatcodes = False  # Track if inside <CheatCodes> section

            for line in lines:
                # Handle <UserdefinedSymbols> section removal
                if "<UserdefinedSymbols>" in line:
                    inside_userdefined_symbols = True  # Start ignoring lines
                    continue
                if "</UserdefinedSymbols>" in line:
                    inside_userdefined_symbols = False  # Stop ignoring lines
                    continue
                if inside_userdefined_symbols:
                    continue  # Skip all lines within the section

                # Handle <CheatCodes> section removal
                if "<CheatCodes>" in line:
                    inside_cheatcodes = True  # Start ignoring lines
                    continue
                if "</CheatCodes>" in line:
                    inside_cheatcodes = False  # Stop ignoring lines
                    continue
                if inside_cheatcodes:
                    continue  # Skip all lines within the section

                # Remove line containing <UserdefinedSymbols/>
                if "<UserdefinedSymbols/>" in line:
                    continue  # Skip this line

                # Check for specific descriptions to update renumbering logic
                if '<Description>"Binds"</Description>' in line:
                    binds_found = True
                    id_counter = 100  # Reset to 3000 after this description
                elif '<Description>"Parkour Mode"</Description>' in line:
                    parkour_mode_found = True
                    id_counter = 200  # Reset to 1000 after this description
                elif '<Description>"Extra"</Description>' in line:
                    extra_found = True
                    id_counter = 300  # Reset to 2000 after this description
                elif '<Description>"Vault Landing Far Height"</Description>' in line:
                    vault_landing_found = True
                    id_counter = 400  # Reset to 3000 after this description

                # Skip lines containing 'LastState'
                if 'LastState' in line:
                    continue  # Do not add this line to processed_lines

                # Remove specific comment lines or comment parts without eliminating every empty line.
                comment_substrings = [
                    "//code from here to '[DISABLE]' will be used to enable the cheat",
                    "//this is allocated memory, you have read,write,execute access",
                    "//place your code here",
                    "//code from here till the end of the code will be used to disable the cheat"
                ]
                remove_line = False  # Flag to indicate if we should skip this line entirely
                for comment in comment_substrings:
                    if comment in line:
                        prefix = line.split(comment)[0]
                        # If the comment is the only thing on the line, mark it to be skipped.
                        if prefix.strip() == "":
                            remove_line = True
                            break
                        else:
                            # Otherwise, remove the comment and keep the rest of the line.
                            line = prefix.rstrip() + "\n"
                if remove_line:
                    continue

                # Check for IDs and replace them using regex
                if '<ID>' in line and '</ID>' in line:
                    line = re.sub(r"<ID>\d+</ID>", renumber_id, line)

                # Remove trailing whitespace
                line = line.rstrip() + '\n' #add newline back after strip

                processed_lines.append(line)

            # Overwrite the original file with processed content
            with open(input_file, 'w') as f:
                f.writelines(processed_lines)

            print(f"Processed file: {input_file}")

print("Processing complete.")