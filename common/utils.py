import os
import logging
import sys
from typing import List

def find_ct_files(folder_path: str, recursive: bool = False) -> List[str]:
    """
    Finds files ending with .ct (case-insensitive) in the given folder.

    Args:
        folder_path: The path to the folder to search.
        recursive: If True, search all subdirectories recursively.

    Returns:
        A list of paths to the .ct files found.
    """
    ct_files = []
    try:
        if recursive:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.ct'):
                        ct_files.append(os.path.join(root, file))
        else:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path) and item.lower().endswith('.ct'):
                    ct_files.append(item_path)
    except FileNotFoundError:
        logging.error(f"Folder not found: {folder_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error accessing folder {folder_path}: {e}")
        sys.exit(1)
    return ct_files