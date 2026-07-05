#!/usr/bin/env bash
set -euo pipefail

pip install --upgrade pip
pip install -r requirements.txt

# hftuner is required for DonutModel (not on PyPI)
if [ ! -f hftuner/donut/model.py ]; then
  rm -rf hftuner
  git clone --depth 1 https://github.com/hftuner/clovaai-donut.git hftuner
fi

echo "Build OK: hftuner + Python deps ready"
