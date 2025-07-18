#!/usr/bin/env python3
"""
Script to send a request to RunPod ComfyUI endpoint.
"""

import requests
import json
import time
import base64
import os
from pathlib import Path

# Configuration
# https://vinvideo-comfyui-outputs.s3-ap-southeast-2.amazonaws.com
API_KEY = os.getenv("RUNPOD_API_KEY", "")
ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"

# Headers for API requests
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def load_workflow():
    """Load the wanLatest workflow JSON."""
    workflow_path = Path(__file__).parent / "wanLatest.json"
    try:
        with open(workflow_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading workflow: {e}")
        return None

def encode_image_to_base64(image_path):
    """Encode an image file to base64 string."""
    try:
        with open(image_path, 'rb') as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            # Just return the raw base64 string without data URI prefix
            return encoded_string
    except Exception as e:
        print(f"Error encoding image: {e}")
        return None

def send_request(workflow, input_images=None, use_async=False):
    """Send a request to the RunPod endpoint."""
    payload = {
        "input": {
            "workflow": workflow
        }
    }
    
    # Add input images if provided
    if input_images:
        payload["input"]["images"] = input_images
    
    endpoint = "/run" if use_async else "/runsync"
    url = f"{BASE_URL}{endpoint}"
    
    print(f"Sending {'async' if use_async else 'sync'} request to RunPod endpoint...")
    print(f"URL: {url}")
    print(f"Payload size: {len(json.dumps(payload))} characters")
    
    try:
        response = requests.post(
            url,
            headers=HEADERS,
            json=payload,
            timeout=300 if not use_async else 30
        )
        
        print(f"Response Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Request successful!")
            
            if use_async:
                job_id = result.get('id')
                print(f"Job ID: {job_id}")
                return poll_job_completion(job_id)
            else:
                return result
        else:
            print(f"❌ Error Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None

def poll_job_completion(job_id, max_wait_time=1200):
    """Poll for job completion."""
    print(f"Polling for job {job_id} completion...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = requests.get(
                f"{BASE_URL}/status/{job_id}",
                headers=HEADERS
            )
            
            if response.status_code == 200:
                status_data = response.json()
                job_status = status_data.get('status')
                print(f"Job status: {job_status}")
                
                if job_status == 'COMPLETED':
                    print("✅ Job completed successfully!")
                    return status_data
                elif job_status == 'FAILED':
                    print("❌ Job failed!")
                    print(json.dumps(status_data, indent=2))
                    return status_data
                elif job_status in ['IN_QUEUE', 'IN_PROGRESS']:
                    print(f"Job is {job_status.lower()}... waiting 10 seconds")
                    time.sleep(10)
                else:
                    print(f"Unknown status: {job_status}")
                    time.sleep(10)
            else:
                print(f"Status check failed: {response.status_code}")
                time.sleep(10)
                
        except Exception as e:
            print(f"Error checking status: {e}")
            time.sleep(10)
    
    print(f"⏰ Job did not complete within {max_wait_time} seconds")
    return None

def save_response(response, filename="response.json"):
    """Save response to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(response, f, indent=2)
    print(f"📁 Response saved to {filename}")

def extract_images(response):
    """Extract and display image information from response."""
    output = response.get('output', {})
    
    if 'images' in output:
        images = output['images']
        print(f"🖼️  Generated {len(images)} images:")
        
        for i, image_data in enumerate(images):
            filename = image_data.get('filename', f'image_{i}')
            image_type = image_data.get('type', 'unknown')
            
            if image_type == 'base64':
                data = image_data.get('data', '')
                if data.startswith('data:'):
                    data = data.split(',', 1)[1]
                
                try:
                    image_bytes = base64.b64decode(data)
                    with open(filename, 'wb') as f:
                        f.write(image_bytes)
                    print(f"  ✅ Saved: {filename} ({len(image_bytes)} bytes)")
                except Exception as e:
                    print(f"  ❌ Failed to save {filename}: {e}")
                    
            elif image_type == 's3_url':
                print(f"  🔗 S3 URL: {image_data.get('data', '')}")
            else:
                print(f"  ❓ Unknown type: {image_type}")
    else:
        print("ℹ️  No images found in response")

def normalize_workflow_node_ids(workflow):
    """
    Normalize workflow node IDs to ensure consistent caching between requests.
    This matches the server-side normalization and helps prevent model reloading.
    """
    import copy
    
    # Create a deep copy to avoid modifying the original
    normalized_workflow = copy.deepcopy(workflow)
    
    # Define standard node ID mappings for common node types
    # These should match the server-side mappings in handler.py
    standard_node_mapping = {
        "LoadDiffusionModelShared //Inspire": "model_loader_1",
        "CLIPLoader": "clip_loader_1", 
        "VAELoader": "vae_loader_1",
        "CLIPVisionLoader": "clip_vision_loader_1",
        "WanImageToVideo": "wan_i2v_1",
        "LoadImage": "load_image_1",
        "CLIPVisionEncode": "clip_vision_encode_1",
        "ModelSamplingSD3": "model_sampling_1",
        "KSampler": "ksampler_1",
        "VAEDecode": "vae_decode_1",
        "CLIPTextEncode": "clip_text_encode",
        "SaveAnimatedWEBP": "save_webp_1",
        "VHS_VideoCombine": "vhs_videocombine_1"
    }
    
    # Create mapping from old node IDs to new standardized IDs
    old_to_new_id = {}
    node_type_counters = {}
    
    # First pass: create the mapping
    for old_id, node_data in workflow.items():
        class_type = node_data.get("class_type", "")
        
        # Check if we have a standard mapping for this node type
        if class_type in standard_node_mapping:
            new_id = standard_node_mapping[class_type]
        else:
            # For other node types, use a counter-based approach
            if class_type not in node_type_counters:
                node_type_counters[class_type] = 1
            else:
                node_type_counters[class_type] += 1
            
            # Create a standardized ID based on class type
            counter = node_type_counters[class_type]
            new_id = f"{class_type.lower().replace(' ', '_')}_{counter}"
        
        old_to_new_id[old_id] = new_id
    
    # Second pass: rebuild workflow with new IDs and update references
    new_workflow = {}
    for old_id, node_data in workflow.items():
        new_id = old_to_new_id[old_id]
        new_node_data = copy.deepcopy(node_data)
        
        # Update input references to use new node IDs
        if "inputs" in new_node_data:
            for input_key, input_value in new_node_data["inputs"].items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    # This looks like a node reference [node_id, output_index]
                    referenced_old_id = str(input_value[0])
                    if referenced_old_id in old_to_new_id:
                        new_node_data["inputs"][input_key] = [
                            old_to_new_id[referenced_old_id], 
                            input_value[1]
                        ]
        
        new_workflow[new_id] = new_node_data
    
    return new_workflow

def main():
    """Main function."""
    print("=" * 60)
    print("🚀 RunPod ComfyUI Image-to-Video Endpoint Test")
    print("=" * 60)
    
    # Load the image-to-video workflow
    workflow = load_workflow()
    if not workflow:
        print("❌ Failed to load image-to-video workflow")
        return
    
    print(f"✅ Loaded image-to-video workflow")
    print(f"📊 Workflow has {len(workflow)} nodes")
    
    # Normalize workflow for consistent model caching
    print("🔄 Normalizing workflow node IDs for better model caching...")
    workflow = normalize_workflow_node_ids(workflow)
    print(f"✅ Workflow normalized with consistent node IDs")
    
    # Normalize workflow node IDs
    workflow = normalize_workflow_node_ids(workflow)
    print("✅ Normalized workflow node IDs")
    
    # Check if input image exists
    image_path = Path(__file__).parent / "test_resources" / "images" / "flux_dev_example.png"
    if image_path.exists():
        print(f"✅ Input image found: {image_path}")
        
        # Encode image and add to payload
        print("🔄 Encoding input image...")
        base64_image = encode_image_to_base64(image_path)
        if base64_image:
            print("✅ Image encoded successfully")
        else:
            print("❌ Failed to encode image")
            return
    else:
        print("⚠️  Input image not found, proceeding without image")
        base64_image = None
    
    # Prepare images array
    input_images = []
    if base64_image:
        input_images.append({
            "name": "flux_dev_example.png",
            "image": base64_image
        })
    
    # Choose request type
    print("\nRequest type:")
    print("  1. Synchronous (wait for completion)")
    print("  2. Asynchronous (submit and poll)")
    
    try:
        req_choice = input("Select (1 or 2, default=2): ").strip()
        use_async = req_choice != "1"  # Default to async since video generation takes time
    except KeyboardInterrupt:
        use_async = True
    
    # Send request
    print(f"📤 Sending {'async' if use_async else 'sync'} request...")
    
    # Use the workflow with images
    response = send_request(workflow, input_images if input_images else None, use_async=use_async)
    
    if response:
        print("\n" + "=" * 60)
        print("📋 RESPONSE")
        print("=" * 60)
        
        # Save response
        filename = f"{'async' if use_async else 'sync'}_response.json"
        save_response(response, filename)
        
        # Extract images/videos
        extract_images(response)
        
        # Show summary
        status = response.get('status', 'unknown')
        execution_time = response.get('executionTime', 0)
        print(f"\n📈 Status: {status}")
        if execution_time:
            print(f"⏱️  Execution time: {execution_time}ms")
            
    else:
        print("❌ No response received")

if __name__ == "__main__":
    main()
