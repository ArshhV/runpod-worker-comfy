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
API_KEY = os.getenv("RUNPOD_API_KEY", "your_runpod_api_key_here")
ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "your_endpoint_id_here")
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

def poll_job_completion(job_id, max_wait_time=600):
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
    
    # Check if input image exists
    image_path = Path(__file__).parent / "test_resources" / "images" / "ComfyUI_00001_.png"
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
            "name": "ComfyUI_00001_.png",
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
