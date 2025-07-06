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

# Function to check overall model status
check_model_status() {
    local model_type="$1"
    echo "worker-comfyui: ========================================"
    echo "worker-comfyui: Checking existing models for $model_type..."
    echo "worker-comfyui: ========================================"
    
    # Check if models directory is mounted (network volume)
    if mountpoint -q /comfyui/models 2>/dev/null; then
        echo "worker-comfyui: ✓ Models directory is mounted as network volume"
    elif [ -d /comfyui/models ]; then
        echo "worker-comfyui: ✓ Models directory exists (local storage)"
    else
        echo "worker-comfyui: Models directory not found, will create it"
    fi
    
    # Show disk usage of models directory if it exists
    if [ -d /comfyui/models ]; then
        local models_size=$(du -sh /comfyui/models 2>/dev/null | cut -f1 || echo "unknown")
        echo "worker-comfyui: Current models directory size: $models_size"
        
        # Count existing model files
        local total_files=$(find /comfyui/models -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" 2>/dev/null | wc -l)
        echo "worker-comfyui: Existing model files found: $total_files"
    fi
    
    echo "worker-comfyui: ========================================"
}

# Create directory structure if it doesn't exist
mkdir -p /comfyui/models/checkpoints /comfyui/models/vae /comfyui/models/unet /comfyui/models/clip /comfyui/models/text_encoders /comfyui/models/diffusion_models /comfyui/models/clip_vision /comfyui/models/upscale_models

# Check model status before proceeding
check_model_status "$MODEL_TYPE"

# Helper function to check if file exists and skip download
check_and_download_with_auth() {
    local token="$1"
    local output="$2"
    local url="$3"
    local filename=$(basename "$output")
    
    # Check if file exists and has reasonable size (> 1MB to avoid partial downloads)
    if [ -f "$output" ]; then
        local file_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
        local file_size_human=$(ls -lh "$output" | awk '{print $5}')
        
        # Check if file size is reasonable (> 1MB = 1048576 bytes)
        if [ "$file_size_bytes" -gt 1048576 ]; then
            echo "worker-comfyui: ✓ File $filename already exists and appears complete (size: $file_size_human)"
            echo "worker-comfyui:   Path: $output"
            return 0
        else
            echo "worker-comfyui: ⚠ File $filename exists but appears incomplete (size: $file_size_human), re-downloading..."
            rm -f "$output"
        fi
    else
        echo "worker-comfyui: File $filename not found, downloading..."
    fi
    
    download_with_auth "$token" "$output" "$url"
}

# Helper function to check if file exists and skip download (no auth)
check_and_download_without_auth() {
    local output="$1"
    local url="$2"
    local filename=$(basename "$output")
    
    # Check if file exists and has reasonable size (> 1MB to avoid partial downloads)
    if [ -f "$output" ]; then
        local file_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
        local file_size_human=$(ls -lh "$output" | awk '{print $5}')
        
        # Check if file size is reasonable (> 1MB = 1048576 bytes)
        if [ "$file_size_bytes" -gt 1048576 ]; then
            echo "worker-comfyui: ✓ File $filename already exists and appears complete (size: $file_size_human)"
            echo "worker-comfyui:   Path: $output"
            return 0
        else
            echo "worker-comfyui: ⚠ File $filename exists but appears incomplete (size: $file_size_human), re-downloading..."
            rm -f "$output"
        fi
    else
        echo "worker-comfyui: File $filename not found, downloading..."
    fi
    
    download_without_auth "$output" "$url"
}

# Helper function to download with authentication and progress
download_with_auth() {
    local token="$1"
    local output="$2"
    local url="$3"
    local filename=$(basename "$output")
    
    echo "worker-comfyui: Starting download of $filename..."
    echo "worker-comfyui: URL: $url"
    echo "worker-comfyui: Destination: $output"
    
    if [ -n "$token" ]; then
        # Create a temporary file for wget output
        local temp_log=$(mktemp)
        
        # Use wget with progress bar and real-time output
        wget --progress=bar:force:noscroll --header="Authorization: Bearer $token" -O "$output" "$url" 2>"$temp_log" &
        local wget_pid=$!
        
        # Monitor the progress in real-time
        (
            while kill -0 "$wget_pid" 2>/dev/null; do
                if [ -f "$temp_log" ]; then
                    tail -f "$temp_log" 2>/dev/null | while IFS= read -r line; do
                        if [[ "$line" =~ [0-9]+% ]]; then
                            echo "worker-comfyui: DOWNLOAD PROGRESS: $line"
                        fi
                    done &
                    local tail_pid=$!
                    wait "$wget_pid" 2>/dev/null
                    kill "$tail_pid" 2>/dev/null
                    break
                fi
                sleep 0.1
            done
        ) &
        
        # Wait for wget to complete
        wait "$wget_pid"
        local exit_code=$?
        
        # Clean up temp file
        rm -f "$temp_log"
        
        if [ $exit_code -eq 0 ]; then
            local file_size=$(ls -lh "$output" | awk '{print $5}')
            echo "worker-comfyui: Successfully downloaded $filename (size: $file_size)"
        else
            echo "worker-comfyui: ERROR - Failed to download $filename"
            exit 1
        fi
    else
        echo "worker-comfyui: ERROR - HUGGINGFACE_ACCESS_TOKEN is required for $url"
        exit 1
    fi
}

# Helper function to download without authentication and progress
download_without_auth() {
    local output="$1"
    local url="$2"
    local filename=$(basename "$output")
    
    echo "worker-comfyui: Starting download of $filename..."
    echo "worker-comfyui: URL: $url"
    echo "worker-comfyui: Destination: $output"
    
    # Create a temporary file for wget output
    local temp_log=$(mktemp)
    
    # Use wget with progress bar and real-time output
    wget --progress=bar:force:noscroll -O "$output" "$url" 2>"$temp_log" &
    local wget_pid=$!
    
    # Monitor the progress in real-time
    (
        while kill -0 "$wget_pid" 2>/dev/null; do
            if [ -f "$temp_log" ]; then
                tail -f "$temp_log" 2>/dev/null | while IFS= read -r line; do
                    if [[ "$line" =~ [0-9]+% ]]; then
                        echo "worker-comfyui: DOWNLOAD PROGRESS: $line"
                    fi
                done &
                local tail_pid=$!
                wait "$wget_pid" 2>/dev/null
                kill "$tail_pid" 2>/dev/null
                break
            fi
            sleep 0.1
        done
    ) &
    
    # Wait for wget to complete
    wait "$wget_pid"
    local exit_code=$?
    
    # Clean up temp file
    rm -f "$temp_log"
    
    if [ $exit_code -eq 0 ]; then
        local file_size=$(ls -lh "$output" | awk '{print $5}')
        echo "worker-comfyui: Successfully downloaded $filename (size: $file_size)"
    else
        echo "worker-comfyui: ERROR - Failed to download $filename"
        exit 1
    fi
}

case "$MODEL_TYPE" in
    "sdxl")
        echo "worker-comfyui: Downloading SDXL models..."
        check_and_download_without_auth "/comfyui/models/checkpoints/sd_xl_base_1.0.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
        check_and_download_without_auth "/comfyui/models/vae/sdxl_vae.safetensors" "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
        check_and_download_without_auth "/comfyui/models/vae/sdxl-vae-fp16-fix.safetensors" "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
        echo "worker-comfyui: SDXL models downloaded successfully."
        ;;
        
    "sd3")
        echo "worker-comfyui: Downloading SD3 models..."
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/checkpoints/sd3_medium_incl_clips_t5xxlfp8.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-3-medium/resolve/main/sd3_medium_incl_clips_t5xxlfp8.safetensors"
        echo "worker-comfyui: SD3 models downloaded successfully."
        ;;
        
    "flux1-schnell")
        echo "worker-comfyui: Downloading FLUX.1-schnell models..."
        check_and_download_without_auth "/comfyui/models/unet/flux1-schnell.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors"
        check_and_download_without_auth "/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        check_and_download_without_auth "/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        check_and_download_without_auth "/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
        echo "worker-comfyui: FLUX.1-schnell models downloaded successfully."
        ;;
        
    "flux1-dev")
        echo "worker-comfyui: Downloading FLUX.1-dev models..."
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/unet/flux1-dev.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
        check_and_download_without_auth "/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        check_and_download_without_auth "/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
        echo "worker-comfyui: FLUX.1-dev models downloaded successfully."
        ;;
        
    "flux1-dev-fp8")
        echo "worker-comfyui: Downloading FLUX.1-dev-fp8 models..."
        check_and_download_without_auth "/comfyui/models/checkpoints/flux1-dev-fp8.safetensors" "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors"
        echo "worker-comfyui: FLUX.1-dev-fp8 models downloaded successfully."
        ;;
        
    "wan")
        echo "worker-comfyui: ========================================"
        echo "worker-comfyui: Starting WAN model downloads..."
        echo "worker-comfyui: This may take several minutes for large models"
        echo "worker-comfyui: ========================================"
        
        # List all models that will be downloaded
        echo "worker-comfyui: Models to download:"
        echo "worker-comfyui:   1. wan_2.1_vae.safetensors"
        echo "worker-comfyui:   2. umt5_xxl_fp8_e4m3fn_scaled.safetensors" 
        echo "worker-comfyui:   3. wan2.1_i2v_720p_14B_bf16.safetensors (LARGE ~27GB)"
        echo "worker-comfyui:   4. clip_vision_h.safetensors"
        echo "worker-comfyui:   5. OmniSR_X2_DIV2K.safetensors"
        echo "worker-comfyui: ========================================"
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/vae/wan_2.1_vae.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        
        echo "worker-comfyui: ========================================"
        echo "worker-comfyui: WARNING: Downloading large model file (~27GB)"
        echo "worker-comfyui: This will take significant time depending on connection"
        echo "worker-comfyui: ========================================"
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/comfyui/models/clip_vision/clip_vision_h.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
        
        check_and_download_without_auth "/comfyui/models/upscale_models/OmniSR_X2_DIV2K.safetensors" "https://huggingface.co/Acly/Omni-SR/resolve/main/OmniSR_X2_DIV2K.safetensors"
        
        echo "worker-comfyui: ========================================"
        echo "worker-comfyui: WAN models downloaded successfully!"
        echo "worker-comfyui: ========================================"
        ;;        *)
        echo "Unknown model type: $MODEL_TYPE"
        echo "Available model types: sdxl, sd3, flux1-schnell, flux1-dev, flux1-dev-fp8, wan"
        echo "Skipping model download."
        ;;
esac

# Final summary
echo "worker-comfyui: ========================================"
echo "worker-comfyui: Model download process completed for $MODEL_TYPE"

if [ -d /comfyui/models ]; then
    local final_size=$(du -sh /comfyui/models 2>/dev/null | cut -f1 || echo "unknown")
    local total_files=$(find /comfyui/models -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" 2>/dev/null | wc -l)
    echo "worker-comfyui: Final models directory size: $final_size"
    echo "worker-comfyui: Total model files: $total_files"
fi

echo "worker-comfyui: ========================================"
