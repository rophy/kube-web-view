#!/bin/bash

# Set up an python 3.12 venv environment with poetry installed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR=$(realpath "$SCRIPT_DIR/../venv")

# This function gets the correct Python 3.12 binary depending on the OS.
get_python_binary() {
  # If "python3.12" exists, use it.
  if command -v python3.12 &> /dev/null; then
    PYTHON_BIN="python3.12"
    return
  fi
  echo "python3.12 not found in PATH, checking other python versions..."

  # If "python3" exists, check its version.
  if command -v python3 &> /dev/null; then
    if python3 --version 2>&1 | grep -q "Python 3.12"; then
      PYTHON_BIN="python3"
      return
    fi
  fi
  echo "python3 not found or not version 3.12, checking other python versions..."

  # If "python" exists, check its version.
  if command -v python &> /dev/null; then
    if python --version 2>&1 | grep -q "Python 3.12"; then
      PYTHON_BIN="python"
      return
    fi
  fi
  echo "python not found or not version 3.12, please install Python 3.12."
  exit 1
}

# Check if venv dir exists.
if [ -d "$VENV_DIR" ]; then
  echo "Virtual environment already exists at $VENV_DIR"
else
  # Get the correct python binary.
  get_python_binary
  echo "Using Python binary: $PYTHON_BIN"

  # Create the venv.
  $PYTHON_BIN -m venv "$VENV_DIR"
  echo "Created virtual environment at $VENV_DIR"
fi

# Activate the venv.
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
echo "Activated virtual environment."

# Install poetry if not already installed.
# https://python-poetry.org/docs/#installing-manually
if ! command -v poetry &> /dev/null; then
  pip install -U pip setuptools wheel
  pip install poetry
  echo "Installed Poetry."
else
  echo "Poetry is already installed."
fi

echo "Setup complete. To activate the virtual environment, run:"
echo "source $VENV_DIR/bin/activate"
echo "Then you can use poetry commands."
echo "To deactivate the virtual environment, run:"
echo "deactivate"
