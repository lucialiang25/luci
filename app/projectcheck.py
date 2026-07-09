"""Project health check for SchoolMail Bridge.

This script reports basic environment information (the Python version and
the current working directory) and confirms that the required project
folders exist. It only *inspects* the project — it never creates or
deletes anything.

Run it with:
    python -m app.projectcheck
"""

import sys
from pathlib import Path


def main() -> None:
    # 1. Show which Python interpreter is running this script.
    #    sys.version holds the full version string, e.g. "3.12.11 ...".
    print("Python version:", sys.version)

    # 2. Show the current working directory.
    #    Path.cwd() returns the folder the program was started from.
    current_dir = Path.cwd()
    print("Current working directory:", current_dir)

    print()  # blank line for readability

    # 3. List the folders the project needs.
    #    Each entry is a Path object (not a plain string), which keeps the
    #    paths clean and works the same on Windows, macOS, and Linux.
    required_folders = [
        Path("config"),
        Path("data"),
        Path("runtime"),
        Path("tests"),
    ]

    # 4. Check each folder and report clearly whether it is present.
    #    is_dir() is True only if the path exists AND is a folder.
    missing_count = 0  # how many folders were not found
    for folder in required_folders:
        if folder.is_dir():
            print(f"[OK]      Found: {folder}/")
        else:
            print(f"[MISSING] Not found: {folder}/")
            missing_count += 1

    print()  # blank line before the summary

    # 5. Print a short summary so the overall result is easy to read.
    if missing_count == 0:
        print("All required folders are present.")
    else:
        print(f"{missing_count} required folder(s) missing. Please create them.")


if __name__ == "__main__":
    main()
