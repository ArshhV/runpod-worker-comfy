#!/usr/bin/env python3
"""
Setup script to configure PyTorch environment variables and temp directories
to prevent the "No usable temporary directory found" error.
"""

import os
import sys
import tempfile
import shutil

def setup_temp_directories():
    """Create and configure temporary directories for PyTorch."""
    temp_dirs = ['/tmp', '/var/tmp', '/usr/tmp', '/comfyui/temp']
    
    for temp_dir in temp_dirs:
        try:
            os.makedirs(temp_dir, mode=0o1777, exist_ok=True)
            print(f"Created/verified temp directory: {temp_dir}")
        except PermissionError:
            print(f"Warning: Cannot create {temp_dir} - permission denied")
        except Exception as e:
            print(f"Warning: Failed to create {temp_dir}: {e}")
    
    # Set environment variables to point to our custom temp directory
    comfy_temp = '/comfyui/temp'
    if os.path.exists(comfy_temp):
        os.environ['TMPDIR'] = comfy_temp
        os.environ['TEMP'] = comfy_temp
        os.environ['TMP'] = comfy_temp
        print(f"Set temp directory environment variables to: {comfy_temp}")
    
    # PyTorch specific environment variables
    os.environ['PYTORCH_JIT_USE_NNC_NOT_NVFUSER'] = '1'
    os.environ['TORCH_COMPILE_DEBUG'] = '0'
    os.environ['PYTORCH_DISABLE_PER_OP_PROFILING'] = '1'
    
    # Disable some PyTorch features that require temp directories
    os.environ['TORCH_USE_CUDA_DSA'] = '0'
    os.environ['TORCH_DISABLE_NUMA'] = '1'
    
    print("PyTorch environment variables configured")

def test_temp_directory():
    """Test if temporary directory is working."""
    try:
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test")
            print(f"Temp directory test successful: {tmp_file.name}")
            return True
    except Exception as e:
        print(f"Temp directory test failed: {e}")
        return False

def main():
    """Main setup function."""
    print("Setting up PyTorch environment...")
    setup_temp_directories()
    
    if test_temp_directory():
        print("Environment setup completed successfully")
        sys.exit(0)
    else:
        print("Environment setup completed with warnings")
        sys.exit(0)  # Don't fail the startup

if __name__ == "__main__":
    main()
