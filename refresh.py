"""Step 7: one command to update everything.

    python3 refresh.py

Downloads anything new from Garmin, re-reads your Apple Health export if you
dropped in a newer export.zip, then rebuilds dashboard.html.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apple
import build
import pull


def main():
    sys.argv = [sys.argv[0]]          # refresh only fetches what's new
    pull.main()

    zip_path = apple.find_export()
    out = os.path.join(HERE, "data", "apple.json")
    if zip_path and (not os.path.exists(out) or
                     os.path.getmtime(zip_path) > os.path.getmtime(out)):
        print("\nFound a newer Apple Health export, reading it...")
        apple.main()

    print()
    build.main()


if __name__ == "__main__":
    main()
