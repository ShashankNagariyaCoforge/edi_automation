#!/bin/bash
# Build script for EDI Mapping Generator

echo "Installing requirements..."
pip install -r requirements.txt

echo "Building executable..."
# Include data directories
pyinstaller --clean --noconfirm --name edi_mapper \
    --add-data "src/ERP_json:src/ERP_json" \
    --add-data "input:input" \
    --add-data "config.yaml:." \
    --collect-all "src" \
    main.py

echo "Build complete. Executable is in dist/edi_mapper/"
chmod +x dist/edi_mapper/edi_mapper
