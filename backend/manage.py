"""Admin commands, run on the server next to the database.

    python -m manage add-athlete "Louis"     # prints the new athlete's access token once
    python -m manage new-token "Louis"       # replaces a lost or leaked token
    python -m manage list
"""
import argparse
import sys

from core import db
from core.auth import hash_token, new_token


def add_athlete(name: str) -> None:
    token = new_token()
    db.execute("INSERT INTO athletes (name, token_hash) VALUES (?, ?)", [name, hash_token(token)])
    print(f"Athlete '{name}' created. Access token (shown only now, enter it in the app):\n{token}")


def replace_token(name: str) -> None:
    token = new_token()
    if not db.execute("UPDATE athletes SET token_hash = ? WHERE name = ?", [hash_token(token), name]):
        sys.exit(f"No athlete named '{name}'")
    print(f"New access token for '{name}' (the old one stops working now):\n{token}")


def list_athletes() -> None:
    for row in db.query("SELECT id, name, strava_connected, sync_status, created_at FROM athletes"):
        print(f"{row['id']:>3}  {row['name']:<20} strava={bool(row['strava_connected'])}"
              f"  sync={row['sync_status']}  since {row['created_at'][:10]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("add-athlete").add_argument("name")
    sub.add_parser("new-token").add_argument("name")
    sub.add_parser("list")
    args = parser.parse_args()

    db.migrate()
    if args.command == "add-athlete":
        add_athlete(args.name)
    elif args.command == "new-token":
        replace_token(args.name)
    else:
        list_athletes()


if __name__ == "__main__":
    main()
