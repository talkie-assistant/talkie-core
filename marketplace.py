"""
Marketplace: list module repos from GitHub org and install them as git submodules.
Used by run_web.py for GET /api/marketplace/modules and POST /api/marketplace/install.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

GITHUB_API_TIMEOUT = 10
MODULE_PREFIX = "talkie-module-"
# Safe shortname: alphanumeric, underscore, hyphen only (no path traversal)
REPO_NAME_RE = re.compile(r"^talkie-module-[a-zA-Z0-9_-]+$")
CACHE_TTL_SEC = 600  # 10 minutes

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _get_github_token() -> str | None:
    return (
        os.environ.get("TALKIE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or None
    )


def _invalidate_cache(org: str) -> None:
    _cache.pop(org, None)


def _list_org_repos(
    org: str,
    timeout: float = GITHUB_API_TIMEOUT,
) -> list[dict[str, Any]]:
    """Fetch public repos for org from GitHub API. Returns [] on error; logs and handles 403."""
    token = _get_github_token()
    url = f"https://api.github.com/orgs/{org}/repos"
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 403:
            logger.warning(
                "GitHub API rate limit (403) for org %s; set GITHUB_TOKEN for higher limit",
                org,
            )
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except requests.exceptions.Timeout:
        logger.warning("GitHub API timeout listing org %s", org)
        return []
    except requests.exceptions.RequestException as e:
        logger.warning("GitHub API error listing org %s: %s", org, e)
        return []
    except Exception as e:
        logger.exception("Unexpected error listing org %s: %s", org, e)
        return []


def _repo_exists_in_org(
    org: str, repo_name: str, timeout: float = GITHUB_API_TIMEOUT
) -> bool:
    """Check that repo exists and belongs to org (GET /repos/org/repo)."""
    token = _get_github_token()
    url = f"https://api.github.com/repos/{org}/{repo_name}"
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.warning("GitHub API error checking repo %s/%s: %s", org, repo_name, e)
        return False


def validate_repo_name(repo_name: str) -> bool:
    """Return True if repo_name matches talkie-module-<safe shortname>."""
    return bool(repo_name and REPO_NAME_RE.match(repo_name))


def shortname_from_repo(repo_name: str) -> str:
    """Derive modules/<shortname> path segment from repo name."""
    if not repo_name.startswith(MODULE_PREFIX):
        return ""
    return repo_name[len(MODULE_PREFIX) :].strip() or ""


def git_available(root: Path) -> bool:
    """Return True if root is the top-level of a git repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            return False
        toplevel = (out.stdout or "").strip()
        return toplevel == str(root.resolve())
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("git_available check failed: %s", e)
        return False


def list_marketplace_modules(
    root: Path,
    org: str,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """
    List modules: org repos with name starting with talkie-module-, merged with installed.
    Each item: repo_name, shortname, description, html_url, clone_url, installed.
    """
    now = time.monotonic()
    if use_cache and org in _cache:
        cached_at, cached_list = _cache[org]
        if now - cached_at < CACHE_TTL_SEC:
            repos = cached_list
        else:
            repos = _list_org_repos(org)
            _cache[org] = (now, repos)
    else:
        repos = _list_org_repos(org)
        _cache[org] = (now, repos)

    installed_ids: set[str] = set()
    try:
        from modules.discovery import get_modules_info

        infos = get_modules_info(root / "modules")
        installed_ids = {m["id"] for m in infos}
    except Exception as e:
        logger.debug("get_modules_info failed for marketplace merge: %s", e)

    result: list[dict[str, Any]] = []
    for r in repos:
        name = r.get("name") or ""
        if not name.startswith(MODULE_PREFIX):
            continue
        short = shortname_from_repo(name)
        if not short:
            continue
        clone_url = r.get("clone_url") or f"https://github.com/{org}/{name}.git"
        result.append(
            {
                "repo_name": name,
                "shortname": short,
                "description": (r.get("description") or "").strip(),
                "html_url": r.get("html_url") or f"https://github.com/{org}/{name}",
                "clone_url": clone_url,
                "installed": short in installed_ids,
            }
        )
    return result


def install_module(
    root: Path,
    org: str,
    repo_name: str,
) -> tuple[bool, str, int]:
    """
    Install a module as a git submodule. Validates repo_name, confirms repo in org,
    then runs git submodule add and git submodule update --init.
    Returns (success, message, status_code).
    """
    if not validate_repo_name(repo_name):
        logger.warning("Marketplace install: invalid repo_name %r", repo_name)
        return False, "Invalid repo name; must be talkie-module-<name>", 400

    shortname = shortname_from_repo(repo_name)
    if not shortname:
        return False, "Invalid repo name", 400

    if not git_available(root):
        logger.warning("Marketplace install: not a git repo at %s", root)
        return False, "Install only works in a git clone of talkie-core", 400

    if not _repo_exists_in_org(org, repo_name):
        logger.warning(
            "Marketplace install: repo %s not found in org %s", repo_name, org
        )
        return False, "Repository not found in organization", 400

    modules_dir = root / "modules"
    target = modules_dir / shortname
    if target.exists():
        logger.info("Marketplace install: already installed at %s", target)
        return False, "already installed", 409

    modules_dir.mkdir(parents=True, exist_ok=True)
    clone_url = f"https://github.com/{org}/{repo_name}.git"
    logger.info("Marketplace install: adding submodule %s -> %s", clone_url, target)

    try:
        add_out = subprocess.run(
            ["git", "submodule", "add", clone_url, str(target)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if add_out.returncode != 0:
            err = (
                add_out.stderr or add_out.stdout or ""
            ).strip() or "submodule add failed"
            logger.warning("Marketplace install: git submodule add failed: %s", err)
            return False, err[:500], 500

        init_out = subprocess.run(
            ["git", "submodule", "update", "--init", str(target)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if init_out.returncode != 0:
            err = (
                init_out.stderr or init_out.stdout or ""
            ).strip() or "submodule update failed"
            logger.warning(
                "Marketplace install: git submodule update --init failed: %s", err
            )
            return False, err[:500], 500

        _invalidate_cache(org)
        logger.info(
            "Marketplace install: success repo_name=%s path=%s", repo_name, target
        )
        return True, f"modules/{shortname}", 200
    except subprocess.TimeoutExpired:
        logger.warning("Marketplace install: timeout")
        return False, "Install timed out", 504
    except Exception as e:
        logger.exception("Marketplace install: %s", e)
        return False, str(e)[:500], 500
