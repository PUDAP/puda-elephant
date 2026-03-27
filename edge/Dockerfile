FROM python:3.14-slim-bookworm

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install system dependencies for USB/serial device access, building Python packages, and OpenCV
RUN apt-get update && apt-get install -y \
  build-essential \
  udev \
  libgl1-mesa-glx \
  libglib2.0-0 \
  libgomp1 \
  && rm -rf /var/lib/apt/lists/*

# Install uv for Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

# Copy the workspace packages
COPY edge/ ./edge/
COPY driver/ ./driver/

# Install dependencies using uv only for this package
WORKDIR /app/edge
RUN uv sync --frozen --no-dev --no-install-project --package first-edge

ENV PYTHONPATH=/app/edge:/app/driver/src

CMD ["uv", "run", "python", "main.py"]

