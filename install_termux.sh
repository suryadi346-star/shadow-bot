#!/data/data/com.termux/files/usr/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  ShadowBot Termux Installer
#  Unified AI Agent — nanobot + NOMAD + OpenClaude
#  Usage: bash install_termux.sh
# ═══════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${CYAN}▶${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

echo -e "${BOLD}${CYAN}"
echo "  ███████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗██████╗  ██████╗ ████████╗"
echo "  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═════╝  ╚═════╝   ╚═╝   "
echo -e "${NC}"
echo -e "${BOLD}  ShadowBot Termux Installer${NC}"
echo -e "  Unified AI Agent (nanobot + NOMAD + OpenClaude)\n"

# ─── Detect environment ────────────────────────────────────────────
if [ -d "/data/data/com.termux" ]; then
    TERMUX=true
    PREFIX="/data/data/com.termux/files/usr"
    log "Detected: Termux on Android"
else
    TERMUX=false
    PREFIX="/usr"
    log "Detected: Linux/macOS"
fi

# ─── Update & install system deps ─────────────────────────────────
log "Updating packages..."
if $TERMUX; then
    pkg update -y 2>/dev/null || warn "pkg update had warnings (ok)"
    log "Installing system dependencies..."
    pkg install -y python git clang make pkg-config libffi openssl 2>/dev/null || \
        warn "Some system packages had issues — continuing"
    # Install ripgrep if available (untuk search tools)
    pkg install -y ripgrep 2>/dev/null || true
else
    # Standard Linux
    if command -v apt-get &>/dev/null; then
        apt-get install -y python3 python3-pip git build-essential libffi-dev libssl-dev 2>/dev/null || true
    fi
fi
ok "System dependencies ready"

# ─── Python version check ─────────────────────────────────────────
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        MAJOR=$(echo $VER | cut -d. -f1)
        MINOR=$(echo $VER | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            ok "Python $VER found at: $(which $cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    err "Python 3.10+ required. Install with: pkg install python"
fi

# ─── pip setup ────────────────────────────────────────────────────
PIP_FLAGS=""
if $TERMUX; then
    PIP_FLAGS=""  # Termux manages its own environment
else
    # Check if we need --break-system-packages
    if $PYTHON_CMD -m pip install --dry-run pip 2>&1 | grep -q "externally-managed"; then
        PIP_FLAGS="--break-system-packages"
    fi
fi

log "Upgrading pip..."
$PYTHON_CMD -m pip install --quiet $PIP_FLAGS --upgrade pip setuptools wheel 2>/dev/null || \
    warn "pip upgrade had warnings — continuing"

# ─── Install ShadowBot ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log "Installing ShadowBot..."
cd "$SCRIPT_DIR"

# Install core dependencies first (safer on low-RAM devices)
log "Installing core dependencies (this may take a few minutes)..."
$PYTHON_CMD -m pip install --quiet $PIP_FLAGS \
    anthropic \
    openai \
    httpx \
    rich \
    prompt_toolkit \
    pydantic \
    click \
    aiohttp \
    aiofiles \
    rank_bm25 \
    sqlite-utils || err "Failed to install core dependencies"
ok "Core dependencies installed"

# Install search package
log "Installing search package..."
$PYTHON_CMD -m pip install --quiet $PIP_FLAGS ddgs 2>/dev/null || \
    $PYTHON_CMD -m pip install --quiet $PIP_FLAGS duckduckgo_search 2>/dev/null || \
    warn "Search package install failed — web search will be unavailable"

# Install shadowbot itself
log "Installing ShadowBot package..."
$PYTHON_CMD -m pip install --quiet $PIP_FLAGS -e . || err "ShadowBot install failed"
ok "ShadowBot installed"

# ─── Create launcher script ────────────────────────────────────────
if $TERMUX; then
    LAUNCH_PATH="$HOME/../usr/bin/shadowbot"
else
    LAUNCH_PATH="/usr/local/bin/shadowbot"
fi

# Make sure the entry point works
if ! command -v shadowbot &>/dev/null; then
    # Create manual launcher
    cat > "$HOME/.local/bin/shadowbot" 2>/dev/null <<LAUNCHER || true
#!/bin/bash
$PYTHON_CMD -m shadowbot.cli "\$@"
LAUNCHER
    chmod +x "$HOME/.local/bin/shadowbot" 2>/dev/null || true

    # Try Termux bin
    cat > "$PREFIX/bin/shadowbot" 2>/dev/null <<LAUNCHER || true
#!/bin/bash
$PYTHON_CMD -m shadowbot.cli "\$@"
LAUNCHER
    chmod +x "$PREFIX/bin/shadowbot" 2>/dev/null || true
fi

# ─── Setup directories ────────────────────────────────────────────
log "Creating ShadowBot directories..."
mkdir -p ~/.shadowbot/workspace
mkdir -p ~/.shadowbot/skills
ok "Directories ready: ~/.shadowbot/"

# ─── Run setup wizard if no config ────────────────────────────────
if [ ! -f ~/.shadowbot/config.json ]; then
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  Quick Configuration${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Available providers:"
    echo "  1. anthropic  (claude-sonnet-4-6)"
    echo "  2. openai     (gpt-4o)"
    echo "  3. ollama     (local, no API key)"
    echo "  4. openrouter (access to 200+ models)"
    echo "  5. deepseek   (cheapest)"
    echo "  6. skip       (configure manually later)"
    echo ""
    read -p "  Choose provider [1-6]: " PROV_CHOICE

    case $PROV_CHOICE in
        1) PROV="anthropic"; KEY_PROMPT="Anthropic API key (from console.anthropic.com): " ;;
        2) PROV="openai"; KEY_PROMPT="OpenAI API key (from platform.openai.com): " ;;
        3) PROV="ollama"; KEY_PROMPT="" ;;
        4) PROV="openrouter"; KEY_PROMPT="OpenRouter API key (from openrouter.ai): " ;;
        5) PROV="deepseek"; KEY_PROMPT="DeepSeek API key (from platform.deepseek.com): " ;;
        *) PROV="skip" ;;
    esac

    if [ "$PROV" != "skip" ]; then
        API_KEY=""
        if [ "$PROV" != "ollama" ] && [ -n "$KEY_PROMPT" ]; then
            read -p "  $KEY_PROMPT" -s API_KEY
            echo ""
        fi

        # Write config
        $PYTHON_CMD -c "
import json, sys
config = {
    'provider': '$PROV',
    'providers': {
        '$PROV': {
            'api_key': '$API_KEY',
            'model': {
                'anthropic': 'claude-sonnet-4-6',
                'openai': 'gpt-4o',
                'ollama': 'llama3.1:8b',
                'openrouter': 'anthropic/claude-sonnet-4-6',
                'deepseek': 'deepseek-chat',
            }.get('$PROV', ''),
            'base_url': {
                'ollama': 'http://localhost:11434/v1',
                'openrouter': 'https://openrouter.ai/api/v1',
                'deepseek': 'https://api.deepseek.com/v1',
            }.get('$PROV', ''),
        }
    },
    'memory_enabled': True,
    'rag_enabled': True,
    'web_search_enabled': True,
    'bash_enabled': True,
}
import pathlib
pathlib.Path('$HOME/.shadowbot').mkdir(parents=True, exist_ok=True)
with open('$HOME/.shadowbot/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('Config saved')
" && ok "Config saved to ~/.shadowbot/config.json"
    else
        warn "Skipped config. Run 'shadowbot setup' to configure later."
    fi
fi

# ─── Final test ────────────────────────────────────────────────────
log "Testing installation..."
TEST_RESULT=$($PYTHON_CMD -c "
from shadowbot.config import load_config
from shadowbot.rag import RAGEngine
from shadowbot.memory import MemoryDB
print('imports OK')
" 2>&1)

if echo "$TEST_RESULT" | grep -q "imports OK"; then
    ok "Import test passed"
else
    warn "Import test had issues: $TEST_RESULT"
fi

# ─── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ShadowBot installed successfully!${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Start:${NC}        shadowbot"
echo -e "  ${BOLD}Setup:${NC}        shadowbot setup"
echo -e "  ${BOLD}Single msg:${NC}   shadowbot agent --message 'hello'"
echo -e "  ${BOLD}Alt command:${NC}  $PYTHON_CMD -m shadowbot.cli"
echo ""
echo -e "  ${BOLD}Slash commands inside agent:${NC}"
echo -e "    /help  /provider  /model  /knowledge add file.txt"
echo ""
