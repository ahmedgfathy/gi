#!/usr/bin/env bash
# ============================================================
#  setup.sh  —  Bootstrap gi on a new machine
#  Run from inside the /gi folder:  bash setup.sh
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}==>${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. Copy .env ──────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        warn ".env created from .env.example — edit it before running the app!"
        warn "  nano .env"
    else
        error ".env.example not found. Clone the repo fresh."
    fi
else
    info ".env already exists — skipping copy"
fi

# ── 2. System dependencies ────────────────────────────────────────────────────
info "Checking system dependencies ..."
command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.11+."
PYVER=$(python3 -c "import sys; print(sys.version_info[:2] >= (3,11))")
[ "$PYVER" = "True" ] || error "Python 3.11+ required."

if ! command -v mysql >/dev/null 2>&1; then
    warn "MySQL client not found. Installing..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -qq && sudo apt-get install -y mysql-server mysql-client
    else
        error "Install MySQL manually: https://dev.mysql.com/downloads/"
    fi
fi

# ── 3. Start MySQL if not running ─────────────────────────────────────────────
if ! mysqladmin ping -u root --silent 2>/dev/null; then
    warn "MySQL not running, attempting to start..."
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl start mysql || warn "Could not start MySQL via systemctl"
    elif command -v service >/dev/null 2>&1; then
        sudo service mysql start || warn "Could not start MySQL via service"
    fi
fi

# ── 4. Load .env to get DB credentials ───────────────────────────────────────
set -a; source .env; set +a
DB_HOST="${DB_HOST:-localhost}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_NAME="${DB_NAME:-photo_manager}"

# ── 5. Create database and import schema ──────────────────────────────────────
info "Setting up MySQL database '${DB_NAME}' ..."

MYSQL_CMD="mysql -h${DB_HOST} -u${DB_USER}"
[ -n "$DB_PASSWORD" ] && MYSQL_CMD="$MYSQL_CMD -p${DB_PASSWORD}"

if ! $MYSQL_CMD -e "USE ${DB_NAME};" 2>/dev/null; then
    info "Creating database '${DB_NAME}' ..."
    $MYSQL_CMD -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
fi

info "Importing schema.sql ..."
$MYSQL_CMD "${DB_NAME}" < schema.sql
info "Database ready."

# ── 6. Create photo directories ───────────────────────────────────────────────
WATCH_DIR="${WATCH_DIR:-/mnt/c/photo}"
info "Creating photo directories under ${WATCH_DIR} ..."
mkdir -p "${WATCH_DIR}/Images" "${WATCH_DIR}/Videos"

# ── 7. Python virtual environment ────────────────────────────────────────────
if [ ! -d .venv ]; then
    info "Creating Python virtual environment (.venv) ..."
    python3 -m venv .venv
fi

info "Activating virtual environment ..."
source .venv/bin/activate

info "Upgrading pip & build tools ..."
pip install --upgrade pip setuptools wheel -q

info "Installing Python dependencies ..."
pip install -r requirements.txt -q

info "Installing project in editable mode ..."
pip install -e ".[dev]" -q

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Next steps:"
echo "    1. Edit .env if you haven't already:   nano .env"
echo "    2. Activate venv:                       source .venv/bin/activate"
echo "    3. Start the photo service:             python photo_service.py"
echo "    4. Start the gallery (web UI):          python gallery.py"
echo "    5. Start file watcher:                  bash watch_photos.sh"
echo ""
