"""Download the latest versions of the dashboard scripts.

Run:  python3 update.py
Never touches .env.local or data/.
"""
import os
import urllib.request

BRANCH_URL = ("https://raw.githubusercontent.com/teestarnes/Training/"
              "claude/garmin-training-dashboard-j3ivrx/")
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with urllib.request.urlopen(BRANCH_URL + "files.txt", timeout=30) as r:
        names = [n.strip() for n in r.read().decode().splitlines() if n.strip()]
    for name in names:
        if name.startswith(".env") or name.startswith("data"):
            continue
        with urllib.request.urlopen(BRANCH_URL + name, timeout=30) as r:
            body = r.read()
        with open(os.path.join(HERE, name), "wb") as f:
            f.write(body)
        print(f"Updated {name}")
    print("All scripts are up to date.")


if __name__ == "__main__":
    main()
