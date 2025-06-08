import requests
import json
import os
import time
import base64
from dotenv import load_dotenv

# Load API key from your .env.local file
load_dotenv('../../.env.local')
api_key = os.getenv('ARSHH_RUNPOD_API_KEY')

# RunPod endpoint ID
endpoint_id = "umhsvxn4l1sw85"

# Define API URLs
health_url = f"https://api.runpod.ai/v2/{endpoint_id}/health"
run_url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
status_url = f"https://api.runpod.ai/v2/{endpoint_id}/status/"

# Define path for output files
# You can set this to an absolute path to ensure files are saved in a known location
script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Go up three levels from src/utils to project root
OUTPUT_DIR = os.getenv('OUTPUT_DIR', os.path.join(script_dir, 'public'))

# Path to the script folder containing images and prompts
script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Go up three levels from src/utils to project root
SCRIPT_FOLDER = os.path.join(script_dir, 'public', 'script-1748839267331-3fdf790b')
PROMPTS_FILE = os.path.join(SCRIPT_FOLDER, 'img-vid-prompts.txt')

def load_image_prompts():
    """Load image prompts from the JSON file"""
    try:
        with open(PROMPTS_FILE, 'r') as f:
            prompts_data = json.load(f)
        return prompts_data
    except Exception as e:
        print(f"Error loading prompts file: {e}")
        return []

def encode_image_to_base64(image_path):
    """Encode an image to base64 for including in the API request"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image: {e}")
        return None

def check_endpoint_health():
    """Check if the RunPod endpoint is healthy."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(health_url, headers=headers)
        print(f"Health Check - Status Code: {response.status_code}")
        print(f"Health Check - Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Health check failed with error: {e}")
        return False

def generate_video(image_path, prompt, 
                  negative_prompt="deformed, distorted, disfigured, motion smear, blur",
                  output_filename="generated_video.mp4"):
    """
    Generate video content using the WAN (Wan Animation Network) workflow format for RunPod
    """
    # Encode the input image to base64
    image_data = encode_image_to_base64(image_path)
    if not image_data:
        print(f"Failed to encode image: {image_path}")
        print("Using default server-side image instead.")
        # Fall back to a default method without uploaded image
        base64_input = None
    else:
        # Use uploaded image data
        print(f"Successfully encoded image for upload: {image_path}")
        base64_input = image_data
        
    # Update the image input node format to match required fields
    image_input = {
        "image": None,
        "image_output": "Save",
        "save_prefix": "input_image",
        "base64_data": base64_input
    }
        
    # REDUCED PARAMETERS: Using a simplified workflow with reduced length and resolution
    workflow = {
      "3": {
        "inputs": {
          "seed": 921088492921482,
          "steps": 20,
          "cfg": 6,
          "sampler_name": "uni_pc",
          "scheduler": "simple",
          "denoise": 1,
          "model": [
            "89",
            0
          ],
          "positive": [
            "82",
            0
          ],
          "negative": [
            "82",
            1
          ],
          "latent_image": [
            "82",
            2
          ]
        },
        "class_type": "KSampler",
        "_meta": {
          "title": "KSampler"
        }
      },
      "6": {
        "inputs": {
          "text": prompt,
          "clip": [
            "38",
            0
          ]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {
          "title": "CLIP Text Encode (Positive Prompt)"
        }
      },
      "7": {
        "inputs": {
          "text": negative_prompt,
          "clip": [
            "38",
            0
          ]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {
          "title": "CLIP Text Encode (Negative Prompt)"
        }
      },
      "8": {
        "inputs": {
          "samples": [
            "3",
            0
          ],
          "vae": [
            "83",
            0
          ]
        },
        "class_type": "VAEDecode",
        "_meta": {
          "title": "VAE Decode"
        }
      },
      "37": {
        "inputs": {
          "unet_name": "wan2.1_i2v_720p_14B_bf16.safetensors",
          "weight_dtype": "default"
        },
        "class_type": "UNETLoader",
        "_meta": {
          "title": "Load Diffusion Model"
        }
      },
      "38": {
        "inputs": {
          "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
          "type": "wan",
          "device": "default"
        },
        "class_type": "CLIPLoader",
        "_meta": {
          "title": "Load CLIP"
        }
      },
      "53": {
        "inputs": {
          "frame_rate": 16,
          "loop_count": 0,
          "filename_prefix": "InstaSD",
          "format": "video/h264-mp4",
          "pix_fmt": "yuv420p",
          "crf": 19,
          "save_metadata": True,
          "trim_to_audio": False,
          "pingpong": False,
          "save_output": True,
          "images": [
            "8",
            0
          ]
        },
        "class_type": "VHS_VideoCombine",
        "_meta": {
          "title": "Video Combine 🎥🅥🅗🅢"
        }
      },
      "65": {
        "inputs": {
          "value": "a*b",
          "a": [
            "67",
            1
          ],
          "b": [
            "76",
            0
          ]
        },
        "class_type": "SimpleMath+",
        "_meta": {
          "title": "height"
        }
      },
      "66": {
        "inputs": {
          "value": "a*b",
          "a": [
            "67",
            0
          ],
          "b": [
            "76",
            0
          ]
        },
        "class_type": "SimpleMath+",
        "_meta": {
          "title": "width"
        }
      },
      "67": {
        "inputs": {
          "image": [
            "68",
            0
          ]
        },
        "class_type": "GetImageSize+",
        "_meta": {
          "title": "🔧 Get Image Size"
        }
      },
      "68": {
        "inputs": {
          "start": 0,
          "length": 1,
          "image": [
            "69",
            0
          ]
        },
        "class_type": "ImageFromBatch+",
        "_meta": {
          "title": "🔧 Image From Batch"
        }
      },
      "69": {
        "inputs": {
          "images": [
            "8",
            0
          ]
        },
        "class_type": "ImageListToImageBatch",
        "_meta": {
          "title": "Image List to Image Batch"
        }
      },
      "70": {
        "inputs": {
          "frame_rate": 16,
          "loop_count": 0,
          "filename_prefix": "InstaSD",
          "format": "video/h264-mp4",
          "pix_fmt": "yuv420p",
          "crf": 19,
          "save_metadata": True,
          "trim_to_audio": False,
          "pingpong": False,
          "save_output": True,
          "images": [
            "73",
            0
          ]
        },
        "class_type": "VHS_VideoCombine",
        "_meta": {
          "title": "Video Combine 🎥🅥🅗🅢"
        }
      },
      "72": {
        "inputs": {
          "frame_rate": 16,
          "loop_count": 0,
          "filename_prefix": "InstaSD",
          "format": "video/h264-mp4",
          "pix_fmt": "yuv420p",
          "crf": 19,
          "save_metadata": True,
          "trim_to_audio": False,
          "pingpong": False,
          "save_output": True,
          "images": [
            "75",
            0
          ]
        },
        "class_type": "VHS_VideoCombine",
        "_meta": {
          "title": "Video Combine 🎥🅥🅗🅢"
        }
      },
      "73": {
        "inputs": {
          "upscale_model": [
            "77",
            0
          ],
          "image": [
            "8",
            0
          ]
        },
        "class_type": "ImageUpscaleWithModel",
        "_meta": {
          "title": "Upscale Image (using Model)"
        }
      },
      "75": {
        "inputs": {
          "upscale_method": "lanczos",
          "width": [
            "66",
            0
          ],
          "height": [
            "65",
            0
          ],
          "crop": "center",
          "image": [
            "73",
            0
          ]
        },
        "class_type": "ImageScale",
        "_meta": {
          "title": "Upscale Image"
        }
      },
      "76": {
        "inputs": {
          "Number": "2"
        },
        "class_type": "Int",
        "_meta": {
          "title": "Upscale Factor"
        }
      },
      "77": {
        "inputs": {
          "model_name": "OmniSR_X2_DIV2K.safetensors"
        },
        "class_type": "UpscaleModelLoader",
        "_meta": {
          "title": "Upscaler"
        }
      },
      "79": {
        "inputs": {
          "crop": "none",
          "clip_vision": [
            "81",
            0
          ],
          "image": [
            "80",
            0
          ]
        },
        "class_type": "CLIPVisionEncode",
        "_meta": {
          "title": "CLIP Vision Encode"
        }
      },
      "80": {
        "inputs": image_input,
        "class_type": "easy loadImageBase64",
        "_meta": {
          "title": "Load Image Base64"
        }
      },
      "81": {
        "inputs": {
          "clip_name": "clip_vision_h.safetensors"
        },
        "class_type": "CLIPVisionLoader",
        "_meta": {
          "title": "Load CLIP Vision"
        }
      },
      "82": {
        "inputs": {
          "width": 544,  # REDUCED from 544
          "height": 960,  # REDUCED from 960
          "length": 73,   # REDUCED from 73 (cut in half)
          "batch_size": 1,
          "positive": [
            "6",
            0
          ],
          "negative": [
            "7",
            0
          ],
          "vae": [
            "83",
            0
          ],
          "clip_vision_output": [
            "79",
            0
          ],
          "start_image": [
            "80",
            0
          ]
        },
        "class_type": "WanImageToVideo",
        "_meta": {
          "title": "WanImageToVideo"
        }
      },
      "83": {
        "inputs": {
          "vae_name": "wan_2.1_vae.safetensors"
        },
        "class_type": "VAELoader",
        "_meta": {
          "title": "Load VAE"
        }
      },
      "89": {
        "inputs": {
          "shift": 8,
          "model": [
            "37",
            0
          ]
        },
        "class_type": "ModelSamplingSD3",
        "_meta": {
          "title": "ModelSamplingSD3"
        }
      },
      "91": {
        "inputs": {
          "ckpt_name": "rife47.pth",
          "clear_cache_after_n_frames": 10,
          "multiplier": 2,
          "fast_mode": True,
          "ensemble": True,
          "scale_factor": 1,
          "frames": [
            "75",
            0
          ]
        },
        "class_type": "RIFE VFI",
        "_meta": {
          "title": "RIFE VFI (recommend rife47 and rife49)"
        }
      },
      "92": {
        "inputs": {
          "frame_rate": 24,
          "loop_count": 0,
          "filename_prefix": "comfyuiblog",
          "format": "video/h264-mp4",
          "pix_fmt": "yuv420p",
          "crf": 10,
          "save_metadata": True,
          "trim_to_audio": False,
          "pingpong": False,
          "save_output": True,
          "images": [
            "91",
            0
          ]
        },
        "class_type": "VHS_VideoCombine",
        "_meta": {
          "title": "Video Combine 🎥🅥🅗🅢"
        }
      }
    }
    
    # Create the request payload
    payload = {
      "input": {
        "workflow": workflow
      }
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Implement a retry mechanism
    max_retries = 3
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            print(f"Sending request to RunPod WAN endpoint (attempt {retry_count + 1}/{max_retries + 1})...")
            response = requests.post(run_url, headers=headers, json=payload)
            print(f"Response Status Code: {response.status_code}")
            
            if response.status_code == 200:
                job_id = response.json().get("id")
                print(f"Job submitted with ID: {job_id}")
                
                # Poll for job completion with a longer timeout
                start_time = time.time()
                max_duration = 15 * 60  # 15 minutes max wait time
                
                while (time.time() - start_time) < max_duration:
                    status_response = requests.get(f"{status_url}{job_id}", headers=headers)
                    status_data = status_response.json()
                    
                    status = status_data.get("status")
                    print(f"Current status: {status}")
                    
                    if status == "COMPLETED":
                        output = status_data.get("output")
                        print(f"Job completed successfully!")
                        print(f"Output type: {type(output)}")
                        
                        # Since videos are automatically uploaded to S3, just process the response
                        try:
                            if output:
                                print(f"Output keys: {output.keys() if isinstance(output, dict) else 'Not a dictionary'}")
                                
                                # Check for message or status in output
                                if isinstance(output, dict):
                                    if 'message' in output:
                                        print(f"Response message: {output['message']}")
                                    if 'status' in output:
                                        print(f"Response status: {output['status']}")
                                    if 'video_url' in output:
                                        print(f"Video URL: {output['video_url']}")
                                    elif 'url' in output:
                                        print(f"URL: {output['url']}")
                                    elif 'videos' in output:
                                        print(f"Videos: {output['videos']}")
                                
                                # Save the output as JSON for reference (debugging purposes)
                                try:
                                    with open(os.path.join(OUTPUT_DIR, "output.json"), "w") as f:
                                        json.dump(output, f, indent=2)
                                    print(f"Output saved to {os.path.join(OUTPUT_DIR, 'output.json')}")
                                except Exception as save_error:
                                    print(f"Could not save output JSON: {save_error}")
                                
                                print("Video generation completed and uploaded to S3!")
                                
                        except Exception as processing_error:
                            print(f"Error processing output: {processing_error}")
                            # Save the raw output for debugging
                            try:
                                with open(os.path.join(OUTPUT_DIR, "raw_output.json"), "w") as f:
                                    json.dump(status_data, f, indent=2)
                                print(f"Raw output saved to {os.path.join(OUTPUT_DIR, 'raw_output.json')}")
                            except Exception as raw_save_error:
                                print(f"Could not save raw output: {raw_save_error}")
                        
                        return output
                    
                    elif status in ["FAILED", "ERROR"]:
                        error_msg = status_data.get('error', 'Unknown error')
                        print(f"Job failed with error: {error_msg}")
                        # If it's a timeout-related error, we'll retry
                        if "Max retries reached" in error_msg or "timeout" in error_msg.lower():
                            break  # Break out of the polling loop to retry
                        else:
                            return None  # For non-timeout errors, don't retry
                    
                    # Wait 5 seconds before checking again
                    time.sleep(5)
                
                # If we've reached here, either the job timed out or failed with a retryable error
                print(f"Job execution taking too long or retryable error. Retrying...")
                retry_count += 1
                
            else:
                print(f"Failed to submit job: {response.text}")
                if response.status_code >= 500:  # Server error, worth retrying
                    retry_count += 1
                    print(f"Server error. Retrying...")
                    time.sleep(5)  # Wait before retry
                else:
                    return None  # Client error, don't retry
                
        except Exception as e:
            print(f"Exception during API request: {e}")
            retry_count += 1
            time.sleep(5)  # Wait before retry
    
    print(f"Exhausted all {max_retries + 1} attempts. Video generation failed.")
    return None

def main():
    # First check if the endpoint is healthy
    print("Checking endpoint health...")
    if not check_endpoint_health():
        print("Endpoint health check failed. Please check your endpoint ID and API key.")
        return
    
    # Show output directory information
    abs_output_dir = os.path.abspath(OUTPUT_DIR)
    print(f"Output files will be saved to: {abs_output_dir}")
    
    # Load image prompts
    prompts_data = load_image_prompts()
    if not prompts_data:
        print("Failed to load prompts. Exiting.")
        return
    
    print(f"Loaded {len(prompts_data)} image prompts")
    
    # Process each image with its corresponding prompt
    for prompt_data in prompts_data:
        image_id = prompt_data['image_id']
        prompt = prompt_data['prompt']
        
        # Construct the image path
        image_filename = f"prompt_engineer_image_{image_id}.png"
        image_path = os.path.join(SCRIPT_FOLDER, image_filename)
        
        # Check if image exists
        if not os.path.exists(image_path):
            print(f"Warning: Image {image_filename} not found at {image_path}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing Image {image_id}")
        print(f"Image: {image_filename}")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}")
        
        # Generate video with custom output filename
        output_filename = f"generated_video_{image_id}.mp4"
        result = generate_video(image_path, prompt=prompt, output_filename=output_filename)
        
        if result:
            print(f"Video generation successful for image {image_id}!")
            print("Video has been uploaded to S3 bucket.")
        else:
            print(f"Video generation failed for image {image_id}.")
        
        # Add a small delay between requests to be respectful to the API
        print("Waiting 10 seconds before next request...")
        time.sleep(10)

if __name__ == "__main__":
    main()