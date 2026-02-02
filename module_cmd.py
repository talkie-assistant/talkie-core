#!/usr/bin/env python3
"""
CLI for module management: list, list-available, add, rm, update (git submodules under modules/).
Production mode (no modules/ on disk, config modules.enabled): list from config; add = pull image from GHCR + update config.
Usage: pipenv run python module_cmd.py list | list-available | add <module> | rm <module> | update [module|all]
Exit codes: 0 = success, 1 = usage/validation error, 2 = git or install failure.
Errors and warnings go to stderr; normal output (list table, success messages) to stdout.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Project root on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Safe shortname for rm/update: alphanumeric, underscore, hyphen only
SHORTNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Production: no modules/ on disk and config has modules.enabled
def _is_production_mode(root: Path) -> bool:
    if os.environ.get("TALKIE_PRODUCTION") == "1":
        return True
    modules_dir = root / "modules"
    if modules_dir.exists() and any(modules_dir.iterdir()):
        return False
    try:
        from config import load_config, get_modules_enabled
        cfg = load_config()
        return bool(get_modules_enabled(cfg))
    except Exception:
        return False


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _is_submodule(root: Path, path: Path) -> bool:
    """Return True if path is a git submodule (listed in .gitmodules and/or git submodule status)."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    rel_str = str(rel).replace("\\", "/")
    gitmodules = root / ".gitmodules"
    if gitmodules.is_file():
        content = gitmodules.read_text(encoding="utf-8", errors="replace")
        if f"path = {rel_str}" in content or f"path={rel_str}" in content:
            return True
    try:
        out = subprocess.run(
            ["git", "submodule", "status", rel_str],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False


def _require_git(root: Path) -> None:
    from marketplace import git_available

    if not git_available(root):
        _err(
            "Not a git repository. Module commands require a git clone of talkie-core."
        )
        sys.exit(2)


def _validate_shortname(module: str) -> bool:
    return bool(module and SHORTNAME_RE.match(module))


def _config_path(root: Path) -> Path:
    return Path(os.environ.get("TALKIE_CONFIG", str(root / "config.yaml")))


def _read_modules_enabled(root: Path) -> list[str]:
    from config import load_config, get_modules_enabled
    cfg = load_config()
    return get_modules_enabled(cfg)


def _write_modules_enabled(root: Path, enabled: list[str]) -> None:
    import yaml
    path = _config_path(root)
    data = {}
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    if "modules" not in data:
        data["modules"] = {}
    data["modules"]["enabled"] = enabled
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def cmd_list(root: Path) -> None:
    if _is_production_mode(root):
        enabled = _read_modules_enabled(root)
        if not enabled:
            print("No modules enabled (edit config modules.enabled).")
            return
        max_id = max(len(x) for x in enabled) if enabled else 4
        max_id = max(max_id, 4)
        fmt = f"{{id:<{max_id}}}  {{state}}"
        print(fmt.format(id="id", state="state"))
        for mid in enabled:
            print(fmt.format(id=mid, state="enabled"))
        return
    try:
        from modules.discovery import get_modules_info

        infos = get_modules_info(root / "modules")
    except Exception as e:
        _err(f"Failed to list modules: {e}")
        sys.exit(1)
    if not infos:
        print("No modules installed.")
        return
    # Human-readable table: id, name, version, description
    max_id = max(len(m.get("id", "")) for m in infos)
    max_name = max(len(m.get("name", "")) for m in infos)
    max_id = max(max_id, 4)
    max_name = max(max_name, 4)
    fmt = f"{{id:<{max_id}}}  {{name:<{max_name}}}  {{version}}  {{description}}"
    print(
        fmt.format(id="id", name="name", version="version", description="description")
    )
    for m in infos:
        print(
            fmt.format(
                id=m.get("id", ""),
                name=m.get("name", ""),
                version=m.get("version", ""),
                description=(m.get("description") or "")[:60],
            )
        )


def cmd_list_available(root: Path, org: str) -> None:
    """List all marketplace modules with an installation state column."""
    try:
        from marketplace import list_marketplace_modules

        modules = list_marketplace_modules(root, org, use_cache=True)
    except Exception as e:
        _err(f"Failed to list available modules: {e}")
        sys.exit(1)
    if _is_production_mode(root):
        enabled = set(_read_modules_enabled(root))
        for m in modules:
            m["installed"] = m.get("shortname", "") in enabled
    if not modules:
        print("No modules available (or GitHub API unreachable).")
        return
    max_id = max(len(m.get("shortname", "")) for m in modules)
    max_id = max(max_id, 4)
    max_desc = min(60, max(len((m.get("description") or "")[:60]) for m in modules))
    max_desc = max(max_desc, 11)
    state_col = "state"
    fmt = f"{{id:<{max_id}}}  {{description:<{max_desc}}}  {{state}}"
    print(fmt.format(id="id", description="description", state=state_col))
    for m in modules:
        short = m.get("shortname", "")
        desc = (m.get("description") or "")[:60]
        state = "installed" if m.get("installed") else "available"
        print(fmt.format(id=short, description=desc, state=state))


def cmd_add(root: Path, module: str, org: str) -> None:
    raw = module.strip()
    if not raw:
        _err("Module name required.")
        sys.exit(1)
    shortname = raw if not raw.startswith("talkie-module-") else raw[len("talkie-module-") :].strip()
    if not shortname or not _validate_shortname(shortname):
        _err("Invalid module name. Use shortname (e.g. speech) or talkie-module-<name>.")
        sys.exit(1)
    repo_name = raw if raw.startswith("talkie-module-") else f"talkie-module-{shortname}"

    if _is_production_mode(root):
        # Production: pull image from GHCR, add to config modules.enabled
        tag = os.environ.get("TALKIE_IMAGE_TAG", "latest")
        image = f"ghcr.io/{org}/talkie-module-{shortname}:{tag}"
        _err(f"Pulling {image}...")
        try:
            out = subprocess.run(
                ["podman", "pull", image],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                _err(out.stderr or out.stdout or "podman pull failed")
                sys.exit(2)
        except FileNotFoundError:
            _err("podman not found. Install podman to add modules in production.")
            sys.exit(2)
        except subprocess.TimeoutExpired:
            _err("podman pull timed out.")
            sys.exit(2)
        enabled = _read_modules_enabled(root)
        if shortname in enabled:
            print(f"Module already enabled: {shortname}")
            print("Run: ./talkie start to start services.")
            return
        enabled.append(shortname)
        _write_modules_enabled(root, enabled)
        print(f"Module added: {shortname} (enabled in config)")
        print("Run: ./talkie start to start the new module (or ./talkie start " + shortname + ")")
        return

    from marketplace import install_module, shortname_from_repo, validate_repo_name

    _require_git(root)
    if not validate_repo_name(repo_name):
        _err(f"Invalid module name: {repo_name}")
        sys.exit(1)
    ok, message, status_code = install_module(root, org, repo_name)
    if ok:
        print(f"Module added: {message}")
        print("Restart the app to load it.")
        return
    if status_code == 409:
        short = shortname_from_repo(repo_name)
        print(f"Already installed: modules/{short}")
        sys.exit(0)
    _err(message)
    sys.exit(2)


def cmd_rm(root: Path, module: str) -> None:
    if not _validate_shortname(module):
        _err("Invalid module name. Use only letters, numbers, underscore, hyphen.")
        sys.exit(1)
    if _is_production_mode(root):
        enabled = _read_modules_enabled(root)
        if module not in enabled:
            _err(f"Module not enabled: {module}")
            sys.exit(1)
        enabled = [x for x in enabled if x != module]
        _write_modules_enabled(root, enabled)
        print(f"Removed module from config: {module}. Run ./talkie stop to stop the container.")
        return
    _require_git(root)
    path = root / "modules" / module
    if not path.exists():
        _err(f"Module not found: {module}")
        sys.exit(1)
    if not _is_submodule(root, path):
        _err("Not a submodule; remove manually if needed.")
        sys.exit(1)
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
        out = subprocess.run(
            ["git", "submodule", "deinit", "-f", rel],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if (
            out.returncode != 0
            and out.stderr
            and "not a submodule" not in out.stderr.lower()
        ):
            _err(out.stderr.strip() or "git submodule deinit failed")
            sys.exit(2)
        out2 = subprocess.run(
            ["git", "rm", "-f", rel],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out2.returncode != 0:
            _err(out2.stderr.strip() or "git rm failed")
            sys.exit(2)
        print(f"Removed module: {module}")
    except subprocess.TimeoutExpired:
        _err("Command timed out.")
        sys.exit(2)
    except FileNotFoundError:
        _err("git not found.")
        sys.exit(2)


def cmd_update(root: Path, module: str | None) -> None:
    if _is_production_mode(root):
        print("Production mode: use ./talkie pull to refresh images.")
        return
    _require_git(root)
    if module is not None and module != "all":
        if not _validate_shortname(module):
            _err("Invalid module name. Use only letters, numbers, underscore, hyphen.")
            sys.exit(1)
        path = root / "modules" / module
        if not path.exists():
            _err(f"Module not found: {module}")
            sys.exit(1)
        rel = str(path.relative_to(root)).replace("\\", "/")
        args = ["git", "submodule", "update", "--init", "--recursive", rel]
    else:
        args = ["git", "submodule", "update", "--init", "--recursive"]
    try:
        out = subprocess.run(
            args,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if out.returncode != 0:
            _err(
                out.stderr.strip()
                or out.stdout.strip()
                or "git submodule update failed"
            )
            sys.exit(2)
        print("Submodules updated.")
    except subprocess.TimeoutExpired:
        _err("Command timed out.")
        sys.exit(2)
    except FileNotFoundError:
        _err("git not found.")
        sys.exit(2)


def main() -> None:
    org = os.environ.get("TALKIE_MARKETPLACE_ORG", "talkie-assistant")
    parser = argparse.ArgumentParser(
        description="Manage modules (git submodules under modules/). Exit: 0=success, 1=usage/validation, 2=git/install failure.",
        prog="module_cmd.py",
    )
    subparsers = parser.add_subparsers(
        dest="subcommand", required=True, help="Subcommand"
    )
    subparsers.add_parser(
        "list", help="List installed modules (id, name, version, description)"
    )
    subparsers.add_parser(
        "list-available", help="List all marketplace modules with installation state"
    )
    add_p = subparsers.add_parser(
        "add", help="Add a module (shortname or talkie-module-<name>)"
    )
    add_p.add_argument(
        "module", help="Shortname (e.g. speech) or repo name (talkie-module-speech)"
    )
    rm_p = subparsers.add_parser(
        "rm", help="Remove a module (shortname; deinit + git rm)"
    )
    rm_p.add_argument("module", help="Shortname (e.g. speech)")
    up_p = subparsers.add_parser("update", help="Init/update submodules (default: all)")
    up_p.add_argument(
        "target", nargs="?", default="all", help="Shortname or 'all' (default: all)"
    )
    args = parser.parse_args()

    if args.subcommand == "list":
        cmd_list(_ROOT)
    elif args.subcommand == "list-available":
        cmd_list_available(_ROOT, org)
    elif args.subcommand == "add":
        cmd_add(_ROOT, args.module, org)
    elif args.subcommand == "rm":
        cmd_rm(_ROOT, args.module)
    elif args.subcommand == "update":
        cmd_update(_ROOT, args.target if args.target != "all" else None)


if __name__ == "__main__":
    main()
