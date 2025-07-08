#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

# Check disk space and warn if low
echo "worker-comfyui: Checking disk space..."
df -h /
AVAILABLE_SPACE=$(df / | tail -1 | awk '{print $4}' | sed 's/[^0-9]//g')
if [ -n "$AVAILABLE_SPACE" ] && [ "$AVAILABLE_SPACE" -lt 5000000 ]; then
    echo "worker-comfyui: WARNING - Less than 5GB disk space available!"
    echo "worker-comfyui: Attempting to clean up space..."
    # Clean up package cache and temporary files
    apt-get clean 2>/dev/null || true
    rm -rf /tmp/* /var/tmp/* 2>/dev/null || true
    rm -rf /var/cache/apt/* 2>/dev/null || true
fi

# Create and configure temp directories with proper permissions
echo "worker-comfyui: Configuring temp directories..."
mkdir -p /tmp /var/tmp /usr/tmp /comfyui/temp
chmod 1777 /tmp /var/tmp /usr/tmp 2>/dev/null || true
chmod 755 /comfyui/temp

# Set comprehensive temp directory environment variables
export TMPDIR=/comfyui/temp
export TEMP=/comfyui/temp
export TMP=/comfyui/temp
export PYTORCH_JIT_USE_NNC_NOT_NVFUSER=1
export TORCH_COMPILE_DEBUG=0

echo "worker-comfyui: Temp directories configured at: $TMPDIR"

# Ensure ComfyUI-Manager runs in offline network mode inside the container
comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

# Download models at runtime if MODEL_TYPE is set
if [ -n "$MODEL_TYPE" ]; then
    echo "worker-comfyui: MODEL_TYPE detected: $MODEL_TYPE"
    echo "worker-comfyui: Checking HuggingFace token availability..."
    if [ -n "$HUGGINGFACE_ACCESS_TOKEN" ]; then
        echo "worker-comfyui: HuggingFace token is set (length: ${#HUGGINGFACE_ACCESS_TOKEN} chars)"
    else
        echo "worker-comfyui: WARNING - HUGGINGFACE_ACCESS_TOKEN is not set"
    fi
    
    echo "worker-comfyui: Checking disk space before model download..."
    df -h /comfyui/models 2>/dev/null || df -h /
    
    if [ -f "/download_models.sh" ]; then
        echo "worker-comfyui: Running model download script"
        chmod +x /download_models.sh
        echo "worker-comfyui: =========================================="
        echo "worker-comfyui: Starting model download process..."
        echo "worker-comfyui: Time: $(date)"
        echo "worker-comfyui: =========================================="
        /download_models.sh
        echo "worker-comfyui: =========================================="
        echo "worker-comfyui: Model download process completed"
        echo "worker-comfyui: Time: $(date)"
        echo "worker-comfyui: =========================================="
        
        echo "worker-comfyui: Checking downloaded models..."
        find /comfyui/models -name "*.safetensors" -exec ls -lh {} \; 2>/dev/null | head -10
    else
        echo "worker-comfyui: Warning - download_models.sh not found"
    fi
else
    echo "worker-comfyui: No MODEL_TYPE specified, skipping model download"
fi

echo "worker-comfyui: Starting ComfyUI"

# Run PyTorch environment setup
echo "worker-comfyui: Setting up PyTorch environment..."
python /setup_pytorch_env.py

# Disable ComfyUI logging to prevent disk space issues
export COMFY_LOG_LEVEL="${COMFY_LOG_LEVEL:-WARNING}"
export PYTHONWARNINGS="ignore"

# Create ComfyUI log directory or disable logging if no space
if ! mkdir -p /comfyui/user 2>/dev/null; then
    echo "worker-comfyui: Cannot create log directory, disabling file logging"
    export COMFY_LOG_LEVEL="ERROR"
fi

# Force high VRAM mode and disable memory optimization
export COMFYUI_FORCE_HIGH_VRAM=1
export COMFYUI_DISABLE_MEMORY_MANAGEMENT=1

# Serve the API and don't shutdown the container
if [ "$SERVE_API_LOCALLY" == "true" ]; then
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --listen --verbose "${COMFY_LOG_LEVEL}" --log-stdout --highvram &

    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
else
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --verbose "${COMFY_LOG_LEVEL}" --log-stdout --highvram &

    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py
fi