#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-family-comm}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

echo "==> Workspace: ${ROOT_DIR}"
echo "==> Conda env: ${CONDA_ENV_NAME}"
echo "==> Python: ${PYTHON_VERSION}"

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found."
  echo "Install Miniconda first, then re-run this script:"
  echo "  cd ~"
  echo "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
  echo "  bash Miniconda3-latest-Linux-x86_64.sh"
  echo "  source ~/.bashrc"
  exit 1
fi

eval "$(conda shell.bash hook)"

echo "==> Installing Ubuntu system build dependencies..."
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  pkg-config \
  libcairo2-dev \
  libgirepository1.0-dev \
  gobject-introspection \
  libdbus-1-dev \
  libglib2.0-dev \
  gir1.2-gtk-3.0 \
  libpq-dev \
  curl \
  git

if ! conda env list | awk '{print $1}' | grep -qx "${CONDA_ENV_NAME}"; then
  echo "==> Creating conda env ${CONDA_ENV_NAME}..."
  conda create -n "${CONDA_ENV_NAME}" "python=${PYTHON_VERSION}" -y
else
  echo "==> Conda env ${CONDA_ENV_NAME} already exists; reusing it."
fi

conda activate "${CONDA_ENV_NAME}"
python --version
python -m pip install --upgrade pip setuptools wheel

install_backend() {
  local project_dir="$1"
  echo
  echo "==> Installing Python dependencies for ${project_dir}"
  cd "${ROOT_DIR}/${project_dir}"
  python -m pip install -e .
  python -m py_compile src/agents/agent.py
}

install_backend "backend/projects"
install_backend "backend/talk_agent"

echo
echo "==> Done."
echo "Use this env before running backend services:"
echo "  conda activate ${CONDA_ENV_NAME}"
echo
echo "Diagnosis agent:"
echo "  cd ${ROOT_DIR}/backend/projects"
echo "  python src/main.py -m http -p 8001"
echo
echo "Daily agent:"
echo "  cd ${ROOT_DIR}/backend/talk_agent"
echo "  python src/main.py -m http -p 8002"
