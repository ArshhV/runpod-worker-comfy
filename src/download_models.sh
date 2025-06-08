#!/bin/bash

# Script to download ComfyUI models at runtime based on environment variables
# Usage: Called automatically by start.sh if MODEL_TYPE is set

set -e

MODEL_TYPE="${MODEL_TYPE}"
HUGGINGFACE_ACCESS_TOKEN="${HUGGINGFACE_ACCESS_TOKEN}"

if [ -z "$MODEL_TYPE" ]; then
  echo "MODEL_TYPE environment variable not set. Skipping model download."
  exit 0
fi

echo "worker-comfyui: Starting model download for type: $MODEL_TYPE"

# Create directory structure if it doesn't exist
mkdir -p /comfyui/models/checkpoints /comfyui/models/vae /comfyui/models/unet /comfyui/models/clip /comfyui/models/text_encoders /comfyui/models/diffusion_models /comfyui/models/clip_vision /comfyui/models/upscale_models

# Helper function to download with authentication
download_with_auth() {
    local token="$1"
    local output="$2"
    local url="$3"
    
    if [ -n "$token" ]; then
        wget -q --header="Authorization: Bearer $token" -O "$output" "$url"
    else
        echo "Error: HUGGINGFACE_ACCESS_TOKEN is required for $url"
        exit 1
    fi
}

# Helper function to download without authentication
download_without_auth() {
    local output="$1"
    local url="$2"
    wget -q -O "$output" "$url"
}

# Download models based on type
case "$MODEL_TYPE" in
    "sdxl")
        echo "Downloading SDXL models..."
        download_without_auth "/comfyui/models/checkpoints/sd_xl_base_1.0.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
        download_without_auth "/comfyui/models/vae/sdxl_vae.safetensors" "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
        download_without_auth "/comfyui/models/vae/sdxl-vae-fp16-fix.safetensors" "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
        echo "SDXL models downloaded successfully."
        ;;
        
    "sd3")
        echo "Downloading SD3 models..."
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/checkpoints/sd3_medium_incl_clips_t5xxlfp8.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-3-medium/resolve/main/sd3_medium_incl_clips_t5xxlfp8.safetensors"
        echo "SD3 models downloaded successfully."
        ;;
        
    "flux1-schnell")
        echo "Downloading FLUX.1-schnell models..."
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/unet/flux1-schnell.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors"
        download_without_auth "/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        download_without_auth "/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
        echo "FLUX.1-schnell models downloaded successfully."
        ;;
        
    "flux1-dev")
        echo "Downloading FLUX.1-dev models..."
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/unet/flux1-dev.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
        download_without_auth "/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        download_without_auth "/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
        echo "FLUX.1-dev models downloaded successfully."
        ;;
        
    "flux1-dev-fp8")
        echo "Downloading FLUX.1-dev-fp8 models..."
        download_without_auth "/comfyui/models/checkpoints/flux1-dev-fp8.safetensors" "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors"
        echo "FLUX.1-dev-fp8 models downloaded successfully."
        ;;
        
    "wan")
        echo "Downloading WAN models..."
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/vae/wan_2.1_vae.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
        download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/clip_vision/clip_vision_h.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
        download_without_auth "/comfyui/models/upscale_models/OmniSR_X2_DIV2K.safetensors" "https://huggingface.co/Acly/Omni-SR/resolve/main/OmniSR_X2_DIV2K.safetensors"
        echo "WAN models downloaded successfully."
        ;;
        
    *)
        echo "Unknown model type: $MODEL_TYPE"
        echo "Available model types: sdxl, sd3, flux1-schnell, flux1-dev, flux1-dev-fp8, wan"
        echo "Skipping model download."
        ;;
esac

echo "worker-comfyui: Model download completed for $MODEL_TYPE"
