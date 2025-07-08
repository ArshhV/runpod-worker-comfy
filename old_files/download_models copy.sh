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
    if mountpoint -q /runpod-volume/comfyui/models 2>/dev/null; then
        echo "worker-comfyui: ✓ Models directory is mounted as network volume"
    elif [ -d /runpod-volume/comfyui/models ]; then
        echo "worker-comfyui: ✓ Models directory exists (network volume storage)"
    else
        echo "worker-comfyui: Models directory not found, will create it"
    fi
    
    # Show disk usage of models directory if it exists
    if [ -d /runpod-volume/comfyui/models ]; then
        local models_size=$(du -sh /runpod-volume/comfyui/models 2>/dev/null | cut -f1 || echo "unknown")
        echo "worker-comfyui: Current models directory size: $models_size"
        
        # Count existing model files
        local total_files=$(find /runpod-volume/comfyui/models -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" 2>/dev/null | wc -l)
        echo "worker-comfyui: Existing model files found: $total_files"
    fi
    
    echo "worker-comfyui: ========================================"
}

# Create directory structure if it doesn't exist
# First ensure network volume is available
if [ ! -d "/runpod-volume" ]; then
    echo "worker-comfyui: ERROR - Network volume not found at /runpod-volume"
    echo "worker-comfyui: Make sure the network volume is properly attached to your endpoint"
    exit 1
fi

mkdir -p /runpod-volume/comfyui/models/checkpoints /runpod-volume/comfyui/models/vae /runpod-volume/comfyui/models/unet /runpod-volume/comfyui/models/clip /runpod-volume/comfyui/models/text_encoders /runpod-volume/comfyui/models/diffusion_models /runpod-volume/comfyui/models/clip_vision /runpod-volume/comfyui/models/upscale_models /runpod-volume/comfyui/models/configs /runpod-volume/comfyui/models/controlnet /runpod-volume/comfyui/models/embeddings /runpod-volume/comfyui/models/loras

# Verify we can write to the network volume
if [ ! -w "/runpod-volume" ]; then
    echo "worker-comfyui: ERROR - Network volume is not writable"
    echo "worker-comfyui: Check network volume permissions and attachment"
    exit 1
fi

# Check model status before proceeding
check_model_status "$MODEL_TYPE"

# Helper function to check if file exists and skip download
check_and_download_with_auth() {
    local token="$1"
    local output="$2"
    local url="$3"
    local filename=$(basename "$output")
    
    # Get expected file size from server first
    local expected_size_bytes=""
    echo "worker-comfyui: Checking remote file size for $filename..."
    local head_response=$(curl -sI --header "Authorization: Bearer $token" "$url" 2>/dev/null || echo "")
    if [ -n "$head_response" ]; then
        expected_size_bytes=$(echo "$head_response" | grep -i "content-length" | awk '{print $2}' | tr -d '\r\n' || echo "")
        if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
            local expected_size_human=$(numfmt --to=iec-i --suffix=B "$expected_size_bytes" 2>/dev/null || echo "unknown")
            echo "worker-comfyui: Expected file size: $expected_size_human ($expected_size_bytes bytes)"
        else
            echo "worker-comfyui: WARNING - Could not determine expected file size from server"
        fi
    else
        echo "worker-comfyui: WARNING - Could not check remote file size"
    fi
    
    # Check if file exists and validate its size
    if [ -f "$output" ]; then
        local file_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
        local file_size_human=$(ls -lh "$output" | awk '{print $5}')
        
        echo "worker-comfyui: Found existing file $filename (size: $file_size_human)"
        
        # If we know the expected size, validate against it
        if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
            local size_diff=$((expected_size_bytes - file_size_bytes))
            local size_diff_abs=${size_diff#-}  # absolute value
            local tolerance=$((expected_size_bytes / 100))  # 1% tolerance
            
            if [ "$size_diff_abs" -le "$tolerance" ]; then
                echo "worker-comfyui: ✓ File $filename already exists and size validation passed"
                echo "worker-comfyui:   Path: $output"
                echo "worker-comfyui:   Expected: $expected_size_bytes bytes, Actual: $file_size_bytes bytes"
                return 0
            else
                echo "worker-comfyui: ✗ File $filename exists but size validation failed!"
                echo "worker-comfyui:   Expected: $expected_size_bytes bytes, Got: $file_size_bytes bytes"
                echo "worker-comfyui:   Difference: $size_diff bytes (tolerance: $tolerance bytes)"
                echo "worker-comfyui: ⚠ File appears corrupted/incomplete, re-downloading..."
                rm -f "$output"
            fi
        else
            # Fallback: check if file size is reasonable (> 1MB) when we can't validate exact size
            if [ "$file_size_bytes" -gt 1048576 ]; then
                echo "worker-comfyui: ✓ File $filename already exists and appears reasonable (size: $file_size_human)"
                echo "worker-comfyui:   Path: $output"
                echo "worker-comfyui:   WARNING: Could not validate exact size, assuming file is complete"
                return 0
            else
                echo "worker-comfyui: ⚠ File $filename exists but appears too small (< 1MB), re-downloading..."
                rm -f "$output"
            fi
        fi
    else
        echo "worker-comfyui: File $filename not found, downloading..."
    fi
    
    download_with_auth "$token" "$output" "$url" "$expected_size_bytes"
}

# Helper function to check if file exists and skip download (no auth)
check_and_download_without_auth() {
    local output="$1"
    local url="$2"
    local filename=$(basename "$output")
    
    # Get expected file size from server first
    local expected_size_bytes=""
    echo "worker-comfyui: Checking remote file size for $filename..."
    local head_response=$(curl -sI "$url" 2>/dev/null || echo "")
    if [ -n "$head_response" ]; then
        expected_size_bytes=$(echo "$head_response" | grep -i "content-length" | awk '{print $2}' | tr -d '\r\n' || echo "")
        if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
            local expected_size_human=$(numfmt --to=iec-i --suffix=B "$expected_size_bytes" 2>/dev/null || echo "unknown")
            echo "worker-comfyui: Expected file size: $expected_size_human ($expected_size_bytes bytes)"
        else
            echo "worker-comfyui: WARNING - Could not determine expected file size from server"
        fi
    else
        echo "worker-comfyui: WARNING - Could not check remote file size"
    fi
    
    # Check if file exists and validate its size
    if [ -f "$output" ]; then
        local file_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
        local file_size_human=$(ls -lh "$output" | awk '{print $5}')
        
        echo "worker-comfyui: Found existing file $filename (size: $file_size_human)"
        
        # If we know the expected size, validate against it
        if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
            local size_diff=$((expected_size_bytes - file_size_bytes))
            local size_diff_abs=${size_diff#-}  # absolute value
            local tolerance=$((expected_size_bytes / 100))  # 1% tolerance
            
            if [ "$size_diff_abs" -le "$tolerance" ]; then
                echo "worker-comfyui: ✓ File $filename already exists and size validation passed"
                echo "worker-comfyui:   Path: $output"
                echo "worker-comfyui:   Expected: $expected_size_bytes bytes, Actual: $file_size_bytes bytes"
                return 0
            else
                echo "worker-comfyui: ✗ File $filename exists but size validation failed!"
                echo "worker-comfyui:   Expected: $expected_size_bytes bytes, Got: $file_size_bytes bytes"
                echo "worker-comfyui:   Difference: $size_diff bytes (tolerance: $tolerance bytes)"
                echo "worker-comfyui: ⚠ File appears corrupted/incomplete, re-downloading..."
                rm -f "$output"
            fi
        else
            # Fallback: check if file size is reasonable (> 1MB) when we can't validate exact size
            if [ "$file_size_bytes" -gt 1048576 ]; then
                echo "worker-comfyui: ✓ File $filename already exists and appears reasonable (size: $file_size_human)"
                echo "worker-comfyui:   Path: $output"
                echo "worker-comfyui:   WARNING: Could not validate exact size, assuming file is complete"
                return 0
            else
                echo "worker-comfyui: ⚠ File $filename exists but appears too small (< 1MB), re-downloading..."
                rm -f "$output"
            fi
        fi
    else
        echo "worker-comfyui: File $filename not found, downloading..."
    fi
    
    download_without_auth "$output" "$url" "$expected_size_bytes"
}

# Helper function to download with authentication and progress
download_with_auth() {
    local token="$1"
    local output="$2"
    local url="$3"
    local expected_size_bytes="$4"  # Optional expected size for validation
    local filename=$(basename "$output")
    local max_retries=3
    local retry_count=0
    
    echo "worker-comfyui: Starting download of $filename..."
    echo "worker-comfyui: URL: $url"
    echo "worker-comfyui: Destination: $output"
    
    if [ -z "$token" ]; then
        echo "worker-comfyui: ERROR - HUGGINGFACE_ACCESS_TOKEN is required for $url"
        exit 1
    fi
    
    while [ $retry_count -lt $max_retries ]; do
        retry_count=$((retry_count + 1))
        
        if [ $retry_count -gt 1 ]; then
            echo "worker-comfyui: Retry attempt $retry_count/$max_retries for $filename"
            # Remove partial file before retry
            rm -f "$output"
            sleep 5  # Brief delay before retry
        fi
        
        # Show periodic status updates during download
        echo "worker-comfyui: Starting download with periodic status updates..."
        
        # Start wget in background with simpler progress monitoring
        timeout 7200 wget --progress=dot:giga --timeout=60 --tries=1 --header="Authorization: Bearer $token" -O "$output" "$url" &
        local wget_pid=$!
        
        # Monitor download progress with file size checks
        local last_size=0
        local stall_count=0
        local start_time=$(date +%s)
        while kill -0 "$wget_pid" 2>/dev/null; do
            sleep 10  # Check every 10 seconds
            
            if [ -f "$output" ]; then
                local current_size=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
                local current_size_human=$(numfmt --to=iec-i --suffix=B "$current_size" 2>/dev/null || echo "${current_size} bytes")
                
                if [ "$current_size" -gt "$last_size" ]; then
                    local downloaded_mb=$((current_size / 1048576))
                    local elapsed=$(($(date +%s) - start_time))
                    local speed_mbps=0
                    if [ $elapsed -gt 0 ]; then
                        speed_mbps=$((downloaded_mb / elapsed))
                    fi
                    
                    local eta_msg=""
                    if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ] && [ $speed_mbps -gt 0 ]; then
                        local remaining_mb=$(((expected_size_bytes - current_size) / 1048576))
                        local eta_seconds=$((remaining_mb / speed_mbps))
                        local eta_minutes=$((eta_seconds / 60))
                        eta_msg=" (ETA: ${eta_minutes}m at ${speed_mbps}MB/s)"
                    fi
                    
                    echo "worker-comfyui: Download progress: $current_size_human downloaded (${downloaded_mb}MB)${eta_msg}"
                    last_size=$current_size
                    stall_count=0
                else
                    stall_count=$((stall_count + 1))
                    echo "worker-comfyui: Download status: $current_size_human (checking progress...)"
                    
                    # If download appears stalled for too long, we'll let wget's timeout handle it
                    if [ $stall_count -ge 6 ]; then  # 60 seconds of no progress
                        echo "worker-comfyui: WARNING: Download appears stalled, but letting wget timeout handle it..."
                        stall_count=0  # Reset to avoid spam
                    fi
                fi
            else
                echo "worker-comfyui: Download starting... (file not yet created)"
            fi
        done
        
        # Wait for wget to complete and get exit code
        wait "$wget_pid"
        local exit_code=$?
        
        # Validate download
        if [ $exit_code -eq 0 ] && [ -f "$output" ]; then
            local actual_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
            local actual_size_human=$(ls -lh "$output" | awk '{print $5}')
            
            echo "worker-comfyui: Download completed. Validating file..."
            echo "worker-comfyui: Actual file size: $actual_size_human ($actual_size_bytes bytes)"
            
            # Validate file size if we know what to expect
            if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
                local size_diff=$((expected_size_bytes - actual_size_bytes))
                local size_diff_abs=${size_diff#-}  # absolute value
                local tolerance=$((expected_size_bytes / 100))  # 1% tolerance
                
                if [ "$size_diff_abs" -le "$tolerance" ]; then
                    echo "worker-comfyui: ✓ File size validation passed (within 1% tolerance)"
                    echo "worker-comfyui: Successfully downloaded $filename (size: $actual_size_human)"
                    return 0
                else
                    echo "worker-comfyui: ✗ File size validation failed!"
                    echo "worker-comfyui: Expected: $expected_size_bytes bytes, Got: $actual_size_bytes bytes"
                    echo "worker-comfyui: Difference: $size_diff bytes (tolerance: $tolerance bytes)"
                    
                    if [ $retry_count -lt $max_retries ]; then
                        echo "worker-comfyui: File appears incomplete, will retry..."
                        continue
                    else
                        echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                        rm -f "$output"
                        exit 1
                    fi
                fi
            else
                # If we can't validate size, at least check it's reasonable (> 1MB)
                if [ "$actual_size_bytes" -gt 1048576 ]; then
                    echo "worker-comfyui: ✓ File appears complete (size > 1MB)"
                    echo "worker-comfyui: Successfully downloaded $filename (size: $actual_size_human)"
                    return 0
                else
                    echo "worker-comfyui: ✗ File appears too small (< 1MB), likely incomplete"
                    
                    if [ $retry_count -lt $max_retries ]; then
                        echo "worker-comfyui: Will retry download..."
                        continue
                    else
                        echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                        rm -f "$output"
                        exit 1
                    fi
                fi
            fi
        else
            echo "worker-comfyui: ✗ Download failed (exit code: $exit_code)"
            
            if [ $retry_count -lt $max_retries ]; then
                echo "worker-comfyui: Will retry download..."
                continue
            else
                echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                rm -f "$output"
                exit 1
            fi
        fi
    done
}

# Helper function to download without authentication and progress
download_without_auth() {
    local output="$1"
    local url="$2"
    local expected_size_bytes="$3"  # Optional expected size for validation
    local filename=$(basename "$output")
    local max_retries=3
    local retry_count=0
    
    echo "worker-comfyui: Starting download of $filename..."
    echo "worker-comfyui: URL: $url"
    echo "worker-comfyui: Destination: $output"
    
    while [ $retry_count -lt $max_retries ]; do
        retry_count=$((retry_count + 1))
        
        if [ $retry_count -gt 1 ]; then
            echo "worker-comfyui: Retry attempt $retry_count/$max_retries for $filename"
            # Remove partial file before retry
            rm -f "$output"
            sleep 5  # Brief delay before retry
        fi
        
        # Show periodic status updates during download
        echo "worker-comfyui: Starting download with periodic status updates..."
        
        # Start wget in background with simpler progress monitoring
        timeout 7200 wget --progress=dot:giga --timeout=60 --tries=1 -O "$output" "$url" &
        local wget_pid=$!
        
        # Monitor download progress with file size checks
        local last_size=0
        local stall_count=0
        local start_time=$(date +%s)
        while kill -0 "$wget_pid" 2>/dev/null; do
            sleep 10  # Check every 10 seconds
            
            if [ -f "$output" ]; then
                local current_size=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
                local current_size_human=$(numfmt --to=iec-i --suffix=B "$current_size" 2>/dev/null || echo "${current_size} bytes")
                
                if [ "$current_size" -gt "$last_size" ]; then
                    local downloaded_mb=$((current_size / 1048576))
                    local elapsed=$(($(date +%s) - start_time))
                    local speed_mbps=0
                    if [ $elapsed -gt 0 ]; then
                        speed_mbps=$((downloaded_mb / elapsed))
                    fi
                    
                    local eta_msg=""
                    if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ] && [ $speed_mbps -gt 0 ]; then
                        local remaining_mb=$(((expected_size_bytes - current_size) / 1048576))
                        local eta_seconds=$((remaining_mb / speed_mbps))
                        local eta_minutes=$((eta_seconds / 60))
                        eta_msg=" (ETA: ${eta_minutes}m at ${speed_mbps}MB/s)"
                    fi
                    
                    echo "worker-comfyui: Download progress: $current_size_human downloaded (${downloaded_mb}MB)${eta_msg}"
                    last_size=$current_size
                    stall_count=0
                else
                    stall_count=$((stall_count + 1))
                    echo "worker-comfyui: Download status: $current_size_human (checking progress...)"
                    
                    # If download appears stalled for too long, we'll let wget's timeout handle it
                    if [ $stall_count -ge 6 ]; then  # 60 seconds of no progress
                        echo "worker-comfyui: WARNING: Download appears stalled, but letting wget timeout handle it..."
                        stall_count=0  # Reset to avoid spam
                    fi
                fi
            else
                echo "worker-comfyui: Download starting... (file not yet created)"
            fi
        done
        
        # Wait for wget to complete and get exit code
        wait "$wget_pid"
        local exit_code=$?
        
        # Validate download
        if [ $exit_code -eq 0 ] && [ -f "$output" ]; then
            local actual_size_bytes=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")
            local actual_size_human=$(ls -lh "$output" | awk '{print $5}')
            
            echo "worker-comfyui: Download completed. Validating file..."
            echo "worker-comfyui: Actual file size: $actual_size_human ($actual_size_bytes bytes)"
            
            # Validate file size if we know what to expect
            if [ -n "$expected_size_bytes" ] && [ "$expected_size_bytes" -gt 0 ]; then
                local size_diff=$((expected_size_bytes - actual_size_bytes))
                local size_diff_abs=${size_diff#-}  # absolute value
                local tolerance=$((expected_size_bytes / 100))  # 1% tolerance
                
                if [ "$size_diff_abs" -le "$tolerance" ]; then
                    echo "worker-comfyui: ✓ File size validation passed (within 1% tolerance)"
                    echo "worker-comfyui: Successfully downloaded $filename (size: $actual_size_human)"
                    return 0
                else
                    echo "worker-comfyui: ✗ File size validation failed!"
                    echo "worker-comfyui: Expected: $expected_size_bytes bytes, Got: $actual_size_bytes bytes"
                    echo "worker-comfyui: Difference: $size_diff bytes (tolerance: $tolerance bytes)"
                    
                    if [ $retry_count -lt $max_retries ]; then
                        echo "worker-comfyui: File appears incomplete, will retry..."
                        continue
                    else
                        echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                        rm -f "$output"
                        exit 1
                    fi
                fi
            else
                # If we can't validate size, at least check it's reasonable (> 1MB)
                if [ "$actual_size_bytes" -gt 1048576 ]; then
                    echo "worker-comfyui: ✓ File appears complete (size > 1MB)"
                    echo "worker-comfyui: Successfully downloaded $filename (size: $actual_size_human)"
                    return 0
                else
                    echo "worker-comfyui: ✗ File appears too small (< 1MB), likely incomplete"
                    
                    if [ $retry_count -lt $max_retries ]; then
                        echo "worker-comfyui: Will retry download..."
                        continue
                    else
                        echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                        rm -f "$output"
                        exit 1
                    fi
                fi
            fi
        else
            echo "worker-comfyui: ✗ Download failed (exit code: $exit_code)"
            
            if [ $retry_count -lt $max_retries ]; then
                echo "worker-comfyui: Will retry download..."
                continue
            else
                echo "worker-comfyui: ERROR - Download failed after $max_retries attempts"
                rm -f "$output"
                exit 1
            fi
        fi
    done
}

case "$MODEL_TYPE" in
    "sdxl")
        echo "worker-comfyui: Downloading SDXL models..."
        check_and_download_without_auth "/runpod-volume/comfyui/models/checkpoints/sd_xl_base_1.0.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/vae/sdxl_vae.safetensors" "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/vae/sdxl-vae-fp16-fix.safetensors" "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors"
        echo "worker-comfyui: SDXL models downloaded successfully."
        ;;
        
    "sd3")
        echo "worker-comfyui: Downloading SD3 models..."
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/checkpoints/sd3_medium_incl_clips_t5xxlfp8.safetensors" "https://huggingface.co/stabilityai/stable-diffusion-3-medium/resolve/main/sd3_medium_incl_clips_t5xxlfp8.safetensors"
        echo "worker-comfyui: SD3 models downloaded successfully."
        ;;
        
    "flux1-schnell")
        echo "worker-comfyui: Downloading FLUX.1-schnell models..."
        check_and_download_without_auth "/runpod-volume/comfyui/models/unet/flux1-schnell.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
        echo "worker-comfyui: FLUX.1-schnell models downloaded successfully."
        ;;
        
    "flux1-dev")
        echo "worker-comfyui: Downloading FLUX.1-dev models..."
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/unet/flux1-dev.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/clip/clip_l.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
        check_and_download_without_auth "/runpod-volume/comfyui/models/clip/t5xxl_fp8_e4m3fn.safetensors" "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/vae/ae.safetensors" "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors"
        echo "worker-comfyui: FLUX.1-dev models downloaded successfully."
        ;;
        
    "flux1-dev-fp8")
        echo "worker-comfyui: Downloading FLUX.1-dev-fp8 models..."
        check_and_download_without_auth "/runpod-volume/comfyui/models/checkpoints/flux1-dev-fp8.safetensors" "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors"
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
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/vae/wan_2.1_vae.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        
        echo "worker-comfyui: ========================================"
        echo "worker-comfyui: WARNING: Downloading large model file (~27GB)"
        echo "worker-comfyui: This will take significant time depending on connection"
        echo "worker-comfyui: ========================================"
        
        # Manual validation for the large model file since HuggingFace may not provide Content-Length
        large_model_path="/runpod-volume/comfyui/models/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
        expected_size_gb=27
        min_size_bytes=$((expected_size_gb * 1000000000 - expected_size_gb * 10000000))  # 27GB - 1% tolerance
        
        if [ -f "$large_model_path" ]; then
            actual_size_bytes=$(stat -f%z "$large_model_path" 2>/dev/null || stat -c%s "$large_model_path" 2>/dev/null || echo "0")
            actual_size_human=$(ls -lh "$large_model_path" | awk '{print $5}')
            
            echo "worker-comfyui: Found existing file wan2.1_i2v_720p_14B_bf16.safetensors (size: $actual_size_human)"
            echo "worker-comfyui: Validating against expected size (~${expected_size_gb}GB, minimum: $(numfmt --to=iec-i --suffix=B $min_size_bytes 2>/dev/null || echo "${min_size_bytes} bytes"))"
            
            if [ "$actual_size_bytes" -ge "$min_size_bytes" ]; then
                echo "worker-comfyui: ✓ File wan2.1_i2v_720p_14B_bf16.safetensors size validation passed"
                echo "worker-comfyui:   Path: $large_model_path"
                echo "worker-comfyui:   Size: $actual_size_human (>= ${expected_size_gb}GB minimum)"
            else
                echo "worker-comfyui: ✗ File wan2.1_i2v_720p_14B_bf16.safetensors is too small!"
                echo "worker-comfyui:   Expected: >= ${expected_size_gb}GB, Got: $actual_size_human"
                echo "worker-comfyui: ⚠ File appears corrupted/incomplete, re-downloading..."
                rm -f "$large_model_path"
                check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "$large_model_path" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
            fi
        else
            echo "worker-comfyui: File wan2.1_i2v_720p_14B_bf16.safetensors not found, downloading..."
            check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "$large_model_path" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_720p_14B_bf16.safetensors"
        fi
        
        check_and_download_with_auth "$HUGGINGFACE_ACCESS_TOKEN" "/runpod-volume/comfyui/models/clip_vision/clip_vision_h.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"
        
        check_and_download_without_auth "/runpod-volume/comfyui/models/upscale_models/OmniSR_X2_DIV2K.safetensors" "https://huggingface.co/Acly/Omni-SR/resolve/main/OmniSR_X2_DIV2K.safetensors"
        
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

if [ -d /runpod-volume/comfyui/models ]; then
    final_size=$(du -sh /runpod-volume/comfyui/models 2>/dev/null | cut -f1 || echo "unknown")
    total_files=$(find /runpod-volume/comfyui/models -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pth" 2>/dev/null | wc -l)
    echo "worker-comfyui: Final models directory size: $final_size"
    echo "worker-comfyui: Total model files: $total_files"
fi

echo "worker-comfyui: ========================================"
