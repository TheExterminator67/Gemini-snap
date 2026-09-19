#!/bin/bash
# Double-click to start Gemini Screen Ask (sets up the venv on first run).
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
python gemini_snap.py
