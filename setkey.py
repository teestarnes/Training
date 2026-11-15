"""Save your Garmin Personal API key into .env.local.

Easiest on iPad (a-Shell), with the key copied to the clipboard:
    pbpaste | python3 setkey.py
Or run  python3 setkey.py  and paste the key when asked.
Run with --check to only see whether a key is saved. The key is never printed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env.local")
NAME = "GARMIN_PERSONAL_API_KEY"


def current_key():
    if not os.path.exists(ENV):
        return ""
    with open(ENV) as f:
        for line in f:
            if line.startswith(NAME + "="):
                return line.split("=", 1)[1].strip()
    return ""


def main():
    if "--check" in sys.argv:
        print("Your key is set." if current_key() else "No key saved yet.")
        return
    if sys.stdin.isatty():
        key = input("Paste your Garmin key, then press Return: ")
    else:
        key = sys.stdin.read()
    key = key.strip().strip('"').strip("'").strip()
    if not key:
        print("Nothing was pasted, so nothing changed. Try again.")
        sys.exit(1)
    if any(c.isspace() for c in key):
        print("That has a space or line break in the middle, which a key never has. "
              "Copy it again and retry.")
        sys.exit(1)
    with open(ENV, "w") as f:
        f.write(f"{NAME}={key}\n")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass
    # A fresh key means any saved token is from the old key.
    tok = os.path.join(HERE, "data", "token.json")
    if os.path.exists(tok):
        os.remove(tok)
    print("Your key is set.")


if __name__ == "__main__":
    main()
