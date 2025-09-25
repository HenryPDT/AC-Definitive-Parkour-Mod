import re
import os
import argparse
import logging
from common.utils import find_ct_files

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class Renumberer:
    def __init__(self):
        self.id_counter = 0

    def renumber_id(self, match):
        new_id = f"<ID>{self.id_counter}</ID>"
        self.id_counter += 1
        return new_id

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments using argparse.
    """
    parser = argparse.ArgumentParser(
        description="Clean all .CT files in a directory by renumbering IDs and removing unnecessary sections."
    )
    parser.add_argument("input_folder", help="Path to the folder containing .CT files to clean.")
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Enable verbose debug logging."
    )
    return parser.parse_args()

def main():
    """
    Main function to clean all .CT files in a directory.
    """
    args = parse_arguments()
    directory = args.input_folder

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    # Validate if the directory exists
    if not os.path.isdir(directory):
        logging.error("The specified directory does not exist: %s", directory)
        exit(1)

    # Find all .CT files in the directory recursively
    logging.info("Scanning for .CT files in: %s", directory)
    ct_files = find_ct_files(directory, recursive=True)

    # Process each .CT file
    for input_file in ct_files:
        renumberer = Renumberer()
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
                renumberer.id_counter = 100  # Reset to 3000 after this description
            elif '<Description>"Parkour Mode"</Description>' in line:
                parkour_mode_found = True
                renumberer.id_counter = 300  # Reset to 1000 after this description
            elif '<Description>"Extra"</Description>' in line:
                extra_found = True
                renumberer.id_counter = 500  # Reset to 2000 after this description
            elif '<Description>"Vault Landing Far Height"</Description>' in line:
                vault_landing_found = True
                renumberer.id_counter = 700  # Reset to 3000 after this description

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
                line = re.sub(r"<ID>\d+</ID>", renumberer.renumber_id, line)

            # Remove trailing whitespace
            line = line.rstrip() + '\n' #add newline back after strip

            processed_lines.append(line)

        # Overwrite the original file with processed content
        if processed_lines:
            # Remove the final newline from the last line only
            processed_lines[-1] = processed_lines[-1].rstrip('\n')
        with open(input_file, 'w') as f:
            f.writelines(processed_lines)

        logging.info("Processed file: %s", input_file)

    logging.info("Processing complete.")

if __name__ == "__main__":
    main()