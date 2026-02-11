import os
import sys

# Add the parent directory to sys.path to allow importing from resources
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from resources.lib.obfuscation import deobfuscate, obfuscate

def main():
    client_id = os.environ.get("TRAKT_CLIENT_ID")
    client_secret = os.environ.get("TRAKT_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Error: TRAKT_CLIENT_ID or TRAKT_CLIENT_SECRET not set.")
        sys.exit(1)

    obfuscated_id = obfuscate(client_id)
    obfuscated_secret = obfuscate(client_secret)

    # Verify logic
    assert deobfuscate(obfuscated_id) == client_id
    assert deobfuscate(obfuscated_secret) == client_secret

    target_file = "resources/lib/traktapi.py"
    with open(target_file, "r") as f:
        content = f.read()

    # Replace placeholders
    new_content = content.replace(
        '"TRAKT_CLIENT_ID_PLACEHOLDER"',
        str(obfuscated_id),
    ).replace(
        '"TRAKT_CLIENT_SECRET_PLACEHOLDER"',
        str(obfuscated_secret),
    )

    if new_content == content:
        print("Error: Could not find placeholders in target file.")
        sys.exit(1)

    with open(target_file, "w") as f:
        f.write(new_content)

    print(f"Successfully injected obfuscated keys into {target_file}")

if __name__ == "__main__":
    main()
