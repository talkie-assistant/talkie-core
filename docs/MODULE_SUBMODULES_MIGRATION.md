# Migrating modules to separate repos (git submodules)

This guide walks through **Section 7** of the self-contained modules refactor: moving the speech, RAG, and browser modules into their own GitHub repos and adding them to the main Talkie repo as git submodules.

---

## Grouping repos on GitHub (container / organization)

**Yes.** The clean way to group the module repos is a **GitHub Organization**:

1. **Create an organization** (e.g. `talkie-app` or your preferred name) at [github.com/organizations/plan](https://github.com/organizations/plan). Public orgs are free.
2. **Create the three module repos** under that org as public repositories:
   - `talkie-module-speech`
   - `talkie-module-rag`
   - `talkie-module-browser`
3. Optionally move or mirror the **main Talkie repo** into the same org so everything lives in one place. You can also keep the main repo under your user and only put the module repos in the org.

**Alternative:** Keep all repos under your user account and use **GitHub Topics** (e.g. `talkie`, `talkie-module`) on each module repo so they show up together in topic search. No org required.

**Repo layout:** Each module repo’s **root** must match the current `modules/<name>/` layout: `config.yaml`, `MODULE.yaml`, `docs/`, `__init__.py`, `server.py`, and any subpackages. The main app will clone each repo into `modules/speech`, `modules/rag`, or `modules/browser`, so the repo root is the module root.

---

## Prerequisites

- Main Talkie repo at a known path (e.g. `~/git/talkie`).
- GitHub org (or user) and three **empty** public repos created:
  - `https://github.com/<org-or-user>/talkie-module-speech`
  - `https://github.com/<org-or-user>/talkie-module-rag`
  - `https://github.com/<org-or-user>/talkie-module-browser`
- Git and shell. Replace `<ORG>` (or your username) in URLs below.

---

## Step 1: Migrate each module into its own repo

Run from the **main Talkie repo root**. Use a separate directory for each module so you can init a new git repo and push.

### Speech

```bash
TALKIE_ROOT=~/git/talkie   # or $(pwd) if you are in the repo
MODULES_ROOT="$TALKIE_ROOT/modules"
WORK=/tmp/talkie-module-speech
rm -rf "$WORK" && mkdir -p "$WORK"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "$MODULES_ROOT/speech/" "$WORK/"
cd "$WORK"
git init
git add .
git commit -m "Initial commit: speech module from Talkie"
git branch -M main
git remote add origin https://github.com/<ORG>/talkie-module-speech.git
git push -u origin main
```

### RAG

```bash
WORK=/tmp/talkie-module-rag
rm -rf "$WORK" && mkdir -p "$WORK"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "$MODULES_ROOT/rag/" "$WORK/"
cd "$WORK"
git init
git add .
git commit -m "Initial commit: RAG module from Talkie"
git branch -M main
git remote add origin https://github.com/<ORG>/talkie-module-rag.git
git push -u origin main
```

### Browser

```bash
WORK=/tmp/talkie-module-browser
rm -rf "$WORK" && mkdir -p "$WORK"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "$MODULES_ROOT/browser/" "$WORK/"
cd "$WORK"
git init
git add .
git commit -m "Initial commit: browser module from Talkie"
git branch -M main
git remote add origin https://github.com/<ORG>/talkie-module-browser.git
git push -u origin main
```

Each new repo must **not** contain `modules/api` or `sdk`; the main app provides those when the module is used inside the Talkie tree.

---

## Step 2: Add submodules to the main repo

From the **main Talkie repo root**:

```bash
cd "$TALKIE_ROOT"

# Remove in-repo module directories (only after Step 1 is pushed)
git rm -rf modules/speech modules/rag modules/browser

# Add each module as a submodule (use your org or username in the URL)
git submodule add https://github.com/<ORG>/talkie-module-speech.git modules/speech
git submodule add https://github.com/<ORG>/talkie-module-rag.git modules/rag
git submodule add https://github.com/<ORG>/talkie-module-browser.git modules/browser

# Commit the change and .gitmodules
git add .gitmodules modules/speech modules/rag modules/browser
git commit -m "Convert speech, rag, browser modules to git submodules"
```

This creates `.gitmodules` and records the current commit of each submodule. Push when ready:

```bash
git push
```

---

## Step 3: Clone instructions for others

After the migration, anyone cloning the main repo must fetch the module submodules:

```bash
# Option A: clone with submodules in one step
git clone --recurse-submodules https://github.com/<ORG>/talkie.git
cd talkie

# Option B: clone then init submodules
git clone https://github.com/<ORG>/talkie.git
cd talkie
git submodule update --init --recursive
```

Update the main repo’s **README** (and wiki) to include these clone instructions.

---

## Step 4: Optional GitHub topics

On each module repo (GitHub → repo → About → gear):

- Add topics: `talkie`, `talkie-module`, and e.g. `speech` / `rag` / `browser` so the repos are easy to find together.

---

## What stays in the main repo

- `modules/api/` (shared client, server, consul, etc.)
- `modules/discovery.py` (and any shared module glue)
- `modules/__init__.py`
- `config.py`, `run_web.py`, `run_module_server.py`, etc.

Discovery still scans `modules/`; submodule directories are normal dirs with `config.yaml` and `MODULE.yaml`. `run_module_server.py` already derives the module list from `discover_modules()`.

---

## Updating submodules later

To pull the latest from a module repo:

```bash
cd modules/speech
git pull origin main
cd ../..
git add modules/speech
git commit -m "Update speech module"
git push
```

Or update all submodules to their remote tracking refs:

```bash
git submodule update --remote --merge
git add modules/speech modules/rag modules/browser
git commit -m "Update module submodules"
git push
```

---

## Summary

| Goal | Approach |
|------|----------|
| **Container / group for module repos** | Create a **GitHub Organization** and add the three public module repos (and optionally the main repo) there. |
| **Migrate modules** | Copy each `modules/<name>/` into a new repo root with `rsync`, `git init`, commit, push. |
| **Main repo** | Remove in-repo `modules/speech`, `rag`, `browser` and add the same paths as submodules; document clone with `--recurse-submodules` or `git submodule update --init --recursive`. |
