#!/usr/bin/env bash
# ============================================================
#  install.sh -- Set up the GI (General Intelligence) project
#  Run from inside the /gi folder:  bash install.sh
# ============================================================
set -e

echo "==> Creating Python virtual environment (.venv) ..."
python3 -m venv .venv

echo "==> Activating virtual environment ..."
source .venv/bin/activate

echo "==> Upgrading pip & build tools ..."
pip install --upgrade pip setuptools wheel

echo "==> Installing core AGI requirements ..."
pip install -r requirements.txt

echo "==> Installing project in editable mode ..."
pip install -e ".[dev]"

echo ""
echo "Installation complete!"
echo "  Activate with:  source .venv/bin/activate"
echo "  Verify with:    python verify.py"
echo "  Run demo with:  python main.py"
