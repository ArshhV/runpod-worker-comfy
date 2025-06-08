# Stage 1: Base image with common dependencies
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 as base

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1 
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget \
    ffmpeg \
    libgl1 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install comfy-cli
RUN pip install comfy-cli

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --cuda-version 11.8 --nvidia --version 0.3.26

# Change working directory to ComfyUI
WORKDIR /comfyui

# Install runpod
RUN pip install runpod requests

# Runtime libs needed by ComfyUI-VideoHelperSuite
RUN pip install --no-cache-dir --force-reinstall \
    opencv-python==4.8.0.76 \
    imageio==2.34.0 \
    imageio-ffmpeg==0.4.8 \
    av==14.3.0

# Support for the network volume
ADD src/extra_model_paths.yaml ./

# Go back to the root
WORKDIR /

# Add scripts
ADD src/start.sh src/restore_snapshot.sh src/rp_handler.py test_input.json ./
RUN chmod +x /start.sh /restore_snapshot.sh

# Optionally copy the snapshot file
ADD *snapshot*.json /

# Restore the snapshot to install custom nodes
RUN /restore_snapshot.sh

# Note: If the base image is used directly, this CMD will take effect
# But for the final stage below, this will be overridden
CMD ["/start.sh"]

# Final stage
FROM base as final

# Change working directory to ComfyUI
WORKDIR /comfyui

# Create necessary directories if they don't exist
RUN mkdir -p models/checkpoints models/vae models/unet models/clip models/text_encoders \
    models/diffusion_models models/clip_vision models/upscale_models

# Copy locally downloaded models
COPY models/ models/

# Go back to the root
WORKDIR /

# Start container - this is the CMD that will be used for the final image
# This is essential for RunPod Serverless to properly start the container
CMD ["/start.sh"]