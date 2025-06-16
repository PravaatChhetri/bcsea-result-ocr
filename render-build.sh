#!/usr/bin/env bash

# Install Tesseract and dependencies
apt-get update && apt-get install -y tesseract-ocr libtesseract-dev

# Install Python packages
pip install -r requirements.txt
