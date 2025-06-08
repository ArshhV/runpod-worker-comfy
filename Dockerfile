# Stage 1: Base image with common dependencies
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04 AS base

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Create and configure temporary directories
RUN mkdir -p /tmp /var/tmp /usr/tmp && \
    chmod 1777 /tmp /var/tmp /usr/tmp

# PyTorch and temp directory environment variables
ENV TMPDIR=/tmp
ENV TEMP=/tmp
ENV TMP=/tmp
ENV PYTORCH_JIT_USE_NNC_NOT_NVFUSER=1
ENV TORCH_COMPILE_DEBUG=0
ENV PYTORCH_DISABLE_PER_OP_PROFILING=1

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install uv (latest) using official installer and create isolated venv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
    && uv venv /opt/venv

# Use the virtual environment for all subsequent commands
ENV PATH="/opt/venv/bin:${PATH}"

# Install comfy-cli + dependencies needed by it to install ComfyUI
RUN uv pip install comfy-cli pip setuptools wheel

# Add script to install custom nodes (needed before using it)
COPY scripts/comfy-node-install.sh /usr/local/bin/comfy-node-install
RUN chmod +x /usr/local/bin/comfy-node-install

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --version 0.3.40 --cuda-version 12.6 --nvidia

# Install custom nodes from Comfy Registry using comfy-node-install
# Note: Using comfy-node-install instead of comfy-cli as recommended in the customization docs
RUN comfy-node-install comfyui-inspire-pack

# Install git-based custom nodes
# ComfyUI-Manager is a popular node manager for ComfyUI
# Check if ComfyUI-Manager exists, if not clone it
RUN cd /comfyui/custom_nodes && \
    (test -d ComfyUI-Manager || git clone https://github.com/ltdrdata/ComfyUI-Manager.git)

# Change working directory to ComfyUI
WORKDIR /comfyui

# Support for the network volume
ADD src/extra_model_paths.yaml ./

# Go back to the root
WORKDIR /

# Install Python runtime dependencies for the handler
RUN uv pip install runpod requests websocket-client

# Add application code and scripts
ADD src/start.sh src/download_models.sh src/setup_pytorch_env.py handler.py test_input.json ./
RUN chmod +x /start.sh /download_models.sh /setup_pytorch_env.py

# Prevent pip from asking for confirmation during uninstall steps in custom nodes
ENV PIP_NO_INPUT=1

# Copy helper script to switch Manager network mode at container start
COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

# Create model directories that will be populated at runtime
RUN mkdir -p /comfyui/models/checkpoints /comfyui/models/vae /comfyui/models/unet /comfyui/models/clip /comfyui/models/text_encoders /comfyui/models/diffusion_models /comfyui/models/clip_vision /comfyui/models/upscale_models

# Create dedicated temp directory for ComfyUI with proper permissions
RUN mkdir -p /comfyui/temp && chmod 755 /comfyui/temp

# Set the default command to run when starting the container
CMD ["/start.sh"]
