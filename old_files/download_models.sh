#!/bin/bash

# Script to download ComfyUI models locally before building Docker image
# Usage: ./download_models.sh <MODEL_TYPE> [HUGGINGFACE_ACCESS_TOKEN]

set -e

MODEL_TYPE="$1"
HUGGINGFACE_ACCESS_TOKEN="$2"

if [ -z "$MODEL_TYPE" ]; then
  echo "Usage: ./download_models.sh <MODEL_TYPE> [HUGGINGFACE_ACCESS_TOKEN]"
  echo "Available model types: sdxl, sd3, flux1-schnell, flux1-dev, testModel, wan"
  exit 1
fi

# Create directory structure
mkdir -p models/checkpoints models/vae models/unet models/clip models/text_encoders models/diffusion_models models/clip_vision models/upscale_models

echo "Downloading models for type: $MODEL_TYPE"

# Check if wget is available, otherwise use curl (for macOS compatibility)
if command -v wget &> /dev/null; then
  download_cmd="wget"
  download_with_auth() {
    wget --header="Authorization: Bearer $1" -O "$2" "$3"
  }
  download_without_auth() {
    wget -O "$1" "$2"
  }
else
  echo "wget not found, using curl instead"
  download_cmd="curl"
  download_with_auth() {
    curl -H "Authorization: Bearer $1" -L "$3" -o "$2"
  }
  download_without_auth() {
    curl -L "$2" -o "$1"
  }
fi

echo "Using $download_cmd for downloads"

# Download models based on type
if [ "$MODEL_TYPE" = "sdxl" ]; then
  download_without_auth "models/checkpoints/sd_xl_base_1.0.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
  download_without_auth "models/vae/sdxl_vae.safetensors" "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
  download_without_auth "models/vae/sdxl-vae-fp16-fix.safetensors" "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
elif [ "$MODEL_TYPE" = "sd3" ]; then
  if [ -z "$HUGGINGFACE_ACCESS_TOKEN" ]; then
    echo "Error: HUGGINGFACE_ACCESS_TOKEN is required for sd3 model"
    exit 1
  fi
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/checkpoints/sd3_medium_incl_clips_t5xxlfp8.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-3-medium/resolve/main/sd3_medium_incl_clips_t5xxlfp8.safetensors"
elif [ "$MODEL_TYPE" = "flux1-schnell" ]; then
  download_without_auth "models/unet/flux1-schnell.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors"
  download_without_auth "models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
  download_without_auth "models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
  download_without_auth "models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
elif [ "$MODEL_TYPE" = "flux1-dev" ]; then
  if [ -z "$HUGGINGFACE_ACCESS_TOKEN" ]; then
    echo "Error: HUGGINGFACE_ACCESS_TOKEN is required for flux1-dev model"
    exit 1
  fi
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/unet/flux1-dev.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
  download_without_auth "models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
  download_without_auth "models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
elif [ "$MODEL_TYPE" = "testModel" ]; then
  if [ -z "$HUGGINGFACE_ACCESS_TOKEN" ]; then
    echo "Error: HUGGINGFACE_ACCESS_TOKEN is required for testModel model"
    exit 1
  fi
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/checkpoints/flux1-dev-fp8.safetensors" "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors"
elif [ "$MODEL_TYPE" = "wan" ]; then
  if [ -z "$HUGGINGFACE_ACCESS_TOKEN" ]; then
    echo "Error: HUGGINGFACE_ACCESS_TOKEN is required for wan model"
    exit 1
  fi
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/vae/wan_2.1_vae.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/clip_vision/clip_vision_h.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
  download_with_auth "${HUGGINGFACE_ACCESS_TOKEN}" "models/upscale_models/OmniSR_X2_DIV2K.safetensors" "https://huggingface.co/Acly/Omni-SR/resolve/main/OmniSR_X2_DIV2K.safetensors"
else
  echo "Unknown model type: $MODEL_TYPE"
  echo "Available model types: sdxl, sd3, flux1-schnell, flux1-dev, testModel, wan"
  exit 1
fi

echo "Model download complete. You can now build the Docker image with:"
echo "docker build --build-arg MODEL_TYPE=$MODEL_TYPE -t comfy-worker:$MODEL_TYPE ."