import os
import pathlib

def make_dir(directory: str) -> str:
    current_working_dir = pathlib.Path.cwd()

    if not os.path.isabs(directory):
        directory = os.path.join(current_working_dir, directory)
    directory = os.path.abspath(directory)

    base_dir = os.path.abspath(current_working_dir)
    if not directory.startswith(base_dir + os.sep) and directory != base_dir:
        raise ValueError(f"Path traversal detected: {directory} is outside {base_dir}")

    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    return directory

def open_file(filename: pathlib.Path) -> bytes:
    with open(filename, "rb") as file:
        file_loaded = file.read()

    return file_loaded



def is_safe_path(base_dir: str, path: str) -> bool:
    # Prevent path traversal and ensure path is within base_dir
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(path)
    return abs_path.startswith(abs_base + os.sep) or abs_path == abs_base


def is_safe_filename(filename: str) -> bool:
    # Disallow forbidden characters for Windows and Unix filesystems
    forbidden = '<>:"/\\|?*\0'
    
    # if metronome_settings["debug"]:
    #     print(f"Checking: {repr(filename)}")
    #     print(f"Forbidden: {any(char in filename for char in forbidden)}")
    #     print(f"Control: {any(ord(char) < 32 for char in filename)}")
    #     print(f"Strip: {filename.strip(' .') != filename}")
    #     print(f"Empty: {not filename}")
    
    if any(char in filename for char in forbidden):
        return False
    # Disallow ASCII control characters
    if any(ord(char) < 32 for char in filename):
        return False
    # Disallow leading/trailing spaces or dots
    if filename.strip(" .") != filename:
        return False
    # Disallow empty filenames
    if not filename:
        return False
    return True