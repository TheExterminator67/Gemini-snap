#!/bin/bash
# Runs Gemini Snap from source. Most people should download the ready-made app from the
# Releases page instead (no Python needed).
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed on this Mac."
  echo "Easiest fix: download the ready-made app from the Releases page of the GitHub repo"
  echo "(no Python needed). Or install Python from https://www.python.org/downloads/"
  read -n 1 -s -r -p "Press any key to close"
  exit 1
fi
if [ ! -x venv/bin/python ]; then
  rm -rf venv
  python3 -m venv venv || { echo "Could not create the environment."; read -n 1 -s -r -p "Press any key"; exit 1; }
fi
source venv/bin/activate
pip install -q -r requirements.txt
python gemini_snap.py
