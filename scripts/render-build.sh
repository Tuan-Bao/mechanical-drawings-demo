#!/usr/bin/env bash
set -euo pipefail

pip install --upgrade pip

python --version
if ! python -c 'import sys; assert sys.version_info[:2] == (3, 11), f"Need Python 3.11, got {sys.version}"'; then
  echo "ERROR: Render must use Python 3.11 (set PYTHON_VERSION=3.11.9 in Dashboard)"
  exit 1
fi

# CPU-only PyTorch (Render has no GPU; avoids huge CUDA wheels)
pip install torch --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt

# hftuner is required for DonutModel (not on PyPI)
if [ ! -f hftuner/donut/model.py ]; then
  rm -rf hftuner
  git clone --depth 1 https://github.com/hftuner/clovaai-donut.git hftuner
fi

echo "Build OK: torch (cpu) + deps + hftuner ready"
