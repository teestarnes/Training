"""Step 1: set up the garmin-dashboard folder on this device.

Run inside a-Shell:  python3 setup.py
Safe to run again: it never overwrites your .env.local.
"""
import os
import sys
import urllib.request

BRANCH_URL = ("https://raw.githubusercontent.com/teestarnes/Training/"
              "claude/garmin-training-dashboard-j3ivrx/")
SCRIPTS = ["garmin.py", "setkey.py", "test_connection.py", "update.py"]

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    v = sys.version_info
    print(f"Python {v.major}.{v.minor}.{v.micro} found.")
    if (v.major, v.minor) < (3, 10):
        print("This needs Python 3.10 or newer. Update a-Shell from the App Store, then try again.")
        sys.exit(1)
    print("  OK, that's new enough.")

    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    print("Made the data/ folder.")

    env = os.path.join(HERE, ".env.local")
    if not os.path.exists(env):
        with open(env, "w") as f:
            f.write("GARMIN_PERSONAL_API_KEY=\n")
        print("Made .env.local (empty for now).")
    else:
        print(".env.local already exists, left it alone.")
    try:
        os.chmod(env, 0o600)
    except OSError:
        pass

    with open(os.path.join(HERE, ".gitignore"), "w") as f:
        f.write(".env.local\ndata/\n")
    print("Made .gitignore (keeps .env.local and data/ private).")

    for name in SCRIPTS:
        with urllib.request.urlopen(BRANCH_URL + name, timeout=30) as r:
            body = r.read()
        with open(os.path.join(HERE, name), "wb") as f:
            f.write(body)
        print(f"Downloaded {name}")

    print("\nStep 1 done. Your project folder is:\n  " + HERE)


if __name__ == "__main__":
    main()
