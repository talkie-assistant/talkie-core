#!/usr/bin/env python3
"""
Generate a GitHub App installation access token for repo sync (e.g. Gitea -> GitHub).

Usage:
  pipenv run python github_app_token.py --app-id 2767835 --pem /path/to/app.pem [--installation-id ID]
  GITHUB_APP_PEM_PATH=/path/to/app.pem pipenv run python github_app_token.py --app-id 2767835

If --installation-id is omitted, lists installations and uses the first one.
Output: the token (or "token <token>" for git credential use).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import jwt
import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GitHub App installation token")
    parser.add_argument("--app-id", type=int, required=True, help="GitHub App ID")
    parser.add_argument("--pem", type=str, default=os.environ.get("GITHUB_APP_PEM_PATH"), help="Path to app private key PEM (or set GITHUB_APP_PEM_PATH)")
    parser.add_argument("--installation-id", type=int, default=None, help="Installation ID (optional; if omitted, list and use first)")
    parser.add_argument("--for-git", action="store_true", help="Print 'token <token>' for git credential helper")
    args = parser.parse_args()

    if not args.pem or not os.path.isfile(args.pem):
        print("error: --pem path to PEM file required (or set GITHUB_APP_PEM_PATH)", file=sys.stderr)
        return 1

    with open(args.pem, "rb") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": str(args.app_id),
    }
    app_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    if isinstance(app_jwt, bytes):
        app_jwt = app_jwt.decode()

    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    installation_id = args.installation_id
    if installation_id is None:
        r = requests.get("https://api.github.com/app/installations", headers=headers, timeout=30)
        r.raise_for_status()
        installations = r.json()
        if not installations:
            print("error: no installations found; install the app on your account first", file=sys.stderr)
            return 1
        installation_id = installations[0]["id"]
        if len(installations) > 1:
            print(f"Using installation_id={installation_id} (first of {len(installations)}). Pass --installation-id to pick another.", file=sys.stderr)

    r = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers,
        json={},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    token = data["token"]

    if args.for_git:
        print(f"token {token}")
    else:
        print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
