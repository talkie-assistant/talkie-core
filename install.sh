#!/usr/bin/env bash
# Talkie installer: production (default) or --developer-mode.
# Production: minimal env at ~/.talkie with talkie script + compose + config; images from GHCR.
# Developer: clone (if needed), submodules, pipenv, config, TALKIE_DEV=1.
# Usage: curl -sSL <url>/install.sh | sh   (production)
#        curl -sSL <url>/install.sh | sh -s -- --developer-mode
# Exit: 0 success, 1 usage/config, 2 runtime/dependency

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Default install base URL when not run from a clone
TALKIE_INSTALL_BASE="${TALKIE_INSTALL_BASE:-https://raw.githubusercontent.com/talkie-assistant/talkie-core/main}"

# Detect if we're inside a talkie-core repo (have talkie script and compose)
_in_repo() {
    [ -f "$1/talkie" ] && [ -f "$1/compose.production.yaml" ] && [ -d "$1/.git" ]
}

# --- Production install ---
install_production() {
    local home="${TALKIE_HOME:-$HOME/.talkie}"
    local src_dir
    src_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
    if _in_repo "$src_dir"; then
        log_info "Installing from repo at $src_dir to $home"
        mkdir -p "$home" "$home/consul" "$home/haproxy" "$home/haproxy/dynamic"
        cp -f "$src_dir/talkie" "$home/talkie"
        cp -f "$src_dir/compose.production.yaml" "$home/"
        cp -f "$src_dir/consul/consul.hcl" "$home/consul/"
        cp -f "$src_dir/haproxy/haproxy.cfg" "$home/haproxy/"
        [ -d "$src_dir/haproxy/dynamic" ] && cp -rf "$src_dir/haproxy/dynamic/"* "$home/haproxy/dynamic/" 2>/dev/null || true
        if [ ! -f "$home/config.yaml" ]; then
            cp -f "$src_dir/config.yaml.example" "$home/config.yaml"
            log_info "Created $home/config.yaml from example"
        else
            log_info "Config already exists at $home/config.yaml; not overwriting"
        fi
    else
        log_info "Downloading Talkie production files to $home"
        mkdir -p "$home" "$home/consul" "$home/haproxy" "$home/haproxy/dynamic"
        local base="$TALKIE_INSTALL_BASE"
        for f in talkie compose.production.yaml config.yaml.example consul/consul.hcl haproxy/haproxy.cfg; do
            local url="$base/$f"
            local out="$home/$f"
            if ! curl -sSL -f -o "$out" "$url" 2>/dev/null; then
                log_error "Download failed: $url"
                exit 2
            fi
        done
        if [ ! -f "$home/config.yaml" ]; then
            cp -f "$home/config.yaml.example" "$home/config.yaml"
            log_info "Created $home/config.yaml from example"
        else
            log_info "Config already exists at $home/config.yaml; not overwriting"
        fi
    fi
    chmod +x "$home/talkie"
    mkdir -p "$home/data"
    log_info "Production install complete. Run: $home/talkie start  (or $home/talkie app)"
    echo ""
    echo "  export TALKIE_HOME=$home"
    echo "  \$TALKIE_HOME/talkie pull   # pull images from GHCR"
    echo "  \$TALKIE_HOME/talkie start  # start all services"
    echo "  \$TALKIE_HOME/talkie app    # start and open Web UI at http://localhost:8765"
}

# --- Developer install ---
install_developer() {
    if ! command -v podman &>/dev/null; then
        log_error "Podman not found. Install: brew install podman (macOS) or see https://podman.io"
        exit 2
    fi
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 not found. Install: brew install python@3.11 (macOS)"
        exit 2
    fi
    if ! command -v pipenv &>/dev/null; then
        log_warn "pipenv not found. Installing..."
        pip3 install --user pipenv || { log_error "Failed to install pipenv"; exit 2; }
        export PATH="$HOME/.local/bin:$PATH"
    fi
    if ! command -v git &>/dev/null; then
        log_error "Git not found. Install git first."
        exit 2
    fi

    local src_dir
    src_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
    local repo_dir="$src_dir"

    if ! _in_repo "$src_dir"; then
        log_info "Not in a talkie-core clone; cloning..."
        local clone_dir="${TALKIE_DEV_CLONE:-$HOME/talkie-core}"
        if [ -d "$clone_dir/.git" ]; then
            repo_dir="$clone_dir"
            log_info "Using existing clone at $repo_dir"
        else
            git clone --depth 1 "https://github.com/talkie-assistant/talkie-core.git" "$clone_dir" || { log_error "Clone failed"; exit 2; }
            repo_dir="$clone_dir"
        fi
    fi

    cd "$repo_dir"
    log_info "Initializing submodules..."
    git submodule update --init --recursive || true
    log_info "Installing Python dependencies..."
    pipenv install --dev || { log_error "pipenv install failed"; exit 2; }
    if [ ! -f "config.yaml" ]; then
        cp -f config.yaml.example config.yaml
        log_info "Created config.yaml from example"
    else
        log_info "config.yaml already exists; not overwriting"
    fi
    if [ ! -f ".env" ]; then
        echo "TALKIE_DEV=1" > .env
        log_info "Created .env with TALKIE_DEV=1"
    else
        if ! grep -q "TALKIE_DEV=1" .env 2>/dev/null; then
            echo "TALKIE_DEV=1" >> .env
            log_info "Appended TALKIE_DEV=1 to .env"
        fi
    fi
    log_info "Developer install complete."
    echo ""
    echo "  cd $repo_dir"
    echo "  ./talkie start   # or ./talkie --dev start (build from source, Web UI via pipenv)"
    echo "  ./talkie app     # start services and run Web UI"
    echo "  ./talkie download   # optional: Vosk, Whisper, Ollama assets"
}

# --- Main ---
DEVELOPER_MODE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --developer-mode|--dev|-d)
            DEVELOPER_MODE=1
            shift
            ;;
        --help|-h)
            echo "Usage: install.sh [--developer-mode|--dev|-d]"
            echo "  Default: production install to ~/.talkie (or TALKIE_HOME)"
            echo "  --developer-mode: full dev env (clone, submodules, pipenv, TALKIE_DEV=1)"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ "$DEVELOPER_MODE" -eq 1 ]; then
    install_developer
else
    if ! command -v podman &>/dev/null; then
        log_error "Podman not found. Install: brew install podman (macOS) or see https://podman.io"
        exit 2
    fi
    install_production
fi
exit 0
