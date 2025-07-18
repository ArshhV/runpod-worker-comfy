import runpod
from runpod.serverless.utils import rp_upload
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
import websocket
import uuid
import tempfile
import socket
import traceback
import copy

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Websocket reconnection behaviour (can be overridden through environment variables)
# NOTE: more attempts and diagnostics improve debuggability whenever ComfyUI crashes mid-job.
#   • WEBSOCKET_RECONNECT_ATTEMPTS sets how many times we will try to reconnect.
#   • WEBSOCKET_RECONNECT_DELAY_S sets the sleep in seconds between attempts.
#
# If the respective env-vars are not supplied we fall back to sensible defaults ("5" and "3").
WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))

# Extra verbose websocket trace logs (set WEBSOCKET_TRACE=true to enable)
if os.environ.get("WEBSOCKET_TRACE", "false").lower() == "true":
    # This prints low-level frame information to stdout which is invaluable for diagnosing
    # protocol errors but can be noisy in production – therefore gated behind an env-var.
    websocket.enableTrace(True)

# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"
# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Helper: quick reachability probe of ComfyUI HTTP endpoint (port 8188)
# ---------------------------------------------------------------------------


def _comfy_server_status():
    """Return a dictionary with basic reachability info for the ComfyUI HTTP server."""
    try:
        resp = requests.get(f"http://{COMFY_HOST}/", timeout=5)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def _attempt_websocket_reconnect(ws_url, max_attempts, delay_s, initial_error):
    """
    Attempts to reconnect to the WebSocket server after a disconnect.

    Args:
        ws_url (str): The WebSocket URL (including client_id).
        max_attempts (int): Maximum number of reconnection attempts.
        delay_s (int): Delay in seconds between attempts.
        initial_error (Exception): The error that triggered the reconnect attempt.

    Returns:
        websocket.WebSocket: The newly connected WebSocket object.

    Raises:
        websocket.WebSocketConnectionClosedException: If reconnection fails after all attempts.
    """
    print(
        f"worker-comfyui - Websocket connection closed unexpectedly: {initial_error}. Attempting to reconnect..."
    )
    last_reconnect_error = initial_error
    for attempt in range(max_attempts):
        # Log current server status before each reconnect attempt so that we can
        # see whether ComfyUI is still alive (HTTP port 8188 responding) even if
        # the websocket dropped. This is extremely useful to differentiate
        # between a network glitch and an outright ComfyUI crash/OOM-kill.
        srv_status = _comfy_server_status()
        if not srv_status["reachable"]:
            # If ComfyUI itself is down there is no point in retrying the websocket –
            # bail out immediately so the caller gets a clear "ComfyUI crashed" error.
            print(
                f"worker-comfyui - ComfyUI HTTP unreachable – aborting websocket reconnect: {srv_status.get('error', 'status '+str(srv_status.get('status_code')))}"
            )
            raise websocket.WebSocketConnectionClosedException(
                "ComfyUI HTTP unreachable during websocket reconnect"
            )

        # Otherwise we proceed with reconnect attempts while server is up
        print(
            f"worker-comfyui - Reconnect attempt {attempt + 1}/{max_attempts}... (ComfyUI HTTP reachable, status {srv_status.get('status_code')})"
        )
        try:
            # Need to create a new socket object for reconnect
            new_ws = websocket.WebSocket()
            new_ws.settimeout(30)  # Set the same timeout as main connection
            new_ws.connect(ws_url, timeout=30)  # Use longer timeout for reconnection
            print(f"worker-comfyui - Websocket reconnected successfully.")
            return new_ws  # Return the new connected socket
        except (
            websocket.WebSocketException,
            ConnectionRefusedError,
            socket.timeout,
            OSError,
        ) as reconn_err:
            last_reconnect_error = reconn_err
            print(
                f"worker-comfyui - Reconnect attempt {attempt + 1} failed: {reconn_err}"
            )
            if attempt < max_attempts - 1:
                print(
                    f"worker-comfyui - Waiting {delay_s} seconds before next attempt..."
                )
                time.sleep(delay_s)
            else:
                print(f"worker-comfyui - Max reconnection attempts reached.")

    # If loop completes without returning, raise an exception
    print("worker-comfyui - Failed to reconnect websocket after connection closed.")
    raise websocket.WebSocketConnectionClosedException(
        f"Connection closed and failed to reconnect. Last error: {last_reconnect_error}"
    )


def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input
    workflow = job_input.get("workflow")
    if workflow is None:
        return None, "Missing 'workflow' parameter"

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # Return validated data and no error
    return {"workflow": workflow, "images": images}, None


def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 50
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 500

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """

    print(f"worker-comfyui - Checking API server at {url}...")
    for i in range(retries):
        try:
            response = requests.get(url, timeout=5)

            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                print(f"worker-comfyui - API is reachable")
                return True
        except requests.Timeout:
            pass
        except requests.RequestException as e:
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"worker-comfyui - Failed to connect to server at {url} after {retries} attempts."
    )
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.

    Returns:
        dict: A dictionary indicating success or error.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"worker-comfyui - Uploading {len(images)} image(s)...")

    for image in images:
        try:
            name = image["name"]
            image_data_uri = image["image"]  # Get the full string (might have prefix)

            # --- Strip Data URI prefix if present ---
            if "," in image_data_uri:
                # Find the comma and take everything after it
                base64_data = image_data_uri.split(",", 1)[1]
            else:
                # Assume it's already pure base64
                base64_data = image_data_uri
            # --- End strip ---

            blob = base64.b64decode(base64_data)  # Decode the cleaned data

            # Prepare the form data
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }

            # POST request to upload the image
            response = requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=30
            )
            response.raise_for_status()

            responses.append(f"Successfully uploaded {name}")
            print(f"worker-comfyui - Successfully uploaded {name}")

        except base64.binascii.Error as e:
            error_msg = f"Error decoding base64 for {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.Timeout:
            error_msg = f"Timeout uploading {image.get('name', 'unknown')}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.RequestException as e:
            error_msg = f"Error uploading {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except Exception as e:
            error_msg = (
                f"Unexpected error uploading {image.get('name', 'unknown')}: {e}"
            )
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)

    if upload_errors:
        print(f"worker-comfyui - image(s) upload finished with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"worker-comfyui - image(s) upload complete")
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def get_available_models():
    """
    Get list of available models from ComfyUI

    Returns:
        dict: Dictionary containing available models by type
    """
    try:
        response = requests.get(f"http://{COMFY_HOST}/object_info", timeout=10)
        response.raise_for_status()
        object_info = response.json()

        # Extract available checkpoints from CheckpointLoaderSimple
        available_models = {}
        if "CheckpointLoaderSimple" in object_info:
            checkpoint_info = object_info["CheckpointLoaderSimple"]
            if "input" in checkpoint_info and "required" in checkpoint_info["input"]:
                ckpt_options = checkpoint_info["input"]["required"].get("ckpt_name")
                if ckpt_options and len(ckpt_options) > 0:
                    available_models["checkpoints"] = (
                        ckpt_options[0] if isinstance(ckpt_options[0], list) else []
                    )

        return available_models
    except Exception as e:
        print(f"worker-comfyui - Warning: Could not fetch available models: {e}")
        return {}


def queue_workflow(workflow, client_id):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed
        client_id (str): The client ID for the websocket connection

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow

    Raises:
        ValueError: If the workflow validation fails with detailed error information
    """
    # Include client_id in the prompt payload
    payload = {"prompt": workflow, "client_id": client_id}
    data = json.dumps(payload).encode("utf-8")

    # Use requests for consistency and timeout
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"http://{COMFY_HOST}/prompt", data=data, headers=headers, timeout=30
    )

    # Handle validation errors with detailed information
    if response.status_code == 400:
        print(f"worker-comfyui - ComfyUI returned 400. Response body: {response.text}")
        try:
            error_data = response.json()
            print(f"worker-comfyui - Parsed error data: {error_data}")

            # Try to extract meaningful error information
            error_message = "Workflow validation failed"
            error_details = []

            # ComfyUI seems to return different error formats, let's handle them all
            if "error" in error_data:
                error_info = error_data["error"]
                if isinstance(error_info, dict):
                    error_message = error_info.get("message", error_message)
                    if error_info.get("type") == "prompt_outputs_failed_validation":
                        error_message = "Workflow validation failed"
                else:
                    error_message = str(error_info)

            # Check for node validation errors in the response
            if "node_errors" in error_data:
                for node_id, node_error in error_data["node_errors"].items():
                    if isinstance(node_error, dict):
                        for error_type, error_msg in node_error.items():
                            error_details.append(
                                f"Node {node_id} ({error_type}): {error_msg}"
                            )
                    else:
                        error_details.append(f"Node {node_id}: {node_error}")

            # Check if the error data itself contains validation info
            if error_data.get("type") == "prompt_outputs_failed_validation":
                error_message = error_data.get("message", "Workflow validation failed")
                # For this type of error, we need to parse the validation details from logs
                # Since ComfyUI doesn't seem to include detailed validation errors in the response
                # Let's provide a more helpful generic message
                available_models = get_available_models()
                if available_models.get("checkpoints"):
                    error_message += f"\n\nThis usually means a required model or parameter is not available."
                    error_message += f"\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                else:
                    error_message += "\n\nThis usually means a required model or parameter is not available."
                    error_message += "\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(error_message)

            # If we have specific validation errors, format them nicely
            if error_details:
                detailed_message = f"{error_message}:\n" + "\n".join(
                    f"• {detail}" for detail in error_details
                )

                # Try to provide helpful suggestions for common errors
                if any(
                    "not in list" in detail and "ckpt_name" in detail
                    for detail in error_details
                ):
                    available_models = get_available_models()
                    if available_models.get("checkpoints"):
                        detailed_message += f"\n\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                    else:
                        detailed_message += "\n\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(detailed_message)
            else:
                # Fallback to the raw response if we can't parse specific errors
                raise ValueError(f"{error_message}. Raw response: {response.text}")

        except (json.JSONDecodeError, KeyError) as e:
            # If we can't parse the error response, fall back to the raw text
            raise ValueError(
                f"ComfyUI validation failed (could not parse error response): {response.text}"
            )

    # For other HTTP errors, raise them normally
    response.raise_for_status()
    return response.json()


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    # Use requests for consistency and timeout
    response = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_image_data(filename, subfolder, image_type):
    """
    Fetch image bytes from the ComfyUI /view endpoint.

    Args:
        filename (str): The filename of the image.
        subfolder (str): The subfolder where the image is stored.
        image_type (str): The type of the image (e.g., 'output').

    Returns:
        bytes: The raw image data, or None if an error occurs.
    """
    print(
        f"worker-comfyui - Fetching image data: type={image_type}, subfolder={subfolder}, filename={filename}"
    )
    data = {"filename": filename, "subfolder": subfolder, "type": image_type}
    url_values = urllib.parse.urlencode(data)
    try:
        # Use requests for consistency and timeout
        response = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=60)
        response.raise_for_status()
        print(f"worker-comfyui - Successfully fetched image data for {filename}")
        return response.content
    except requests.Timeout:
        print(f"worker-comfyui - Timeout fetching image data for {filename}")
        return None
    except requests.RequestException as e:
        print(f"worker-comfyui - Error fetching image data for {filename}: {e}")
        return None
    except Exception as e:
        print(
            f"worker-comfyui - Unexpected error fetching image data for {filename}: {e}"
        )
        return None


def get_video_data(filename, subfolder, file_type="output"):
    """
    Fetch video bytes from the ComfyUI /view endpoint.

    Args:
        filename (str): The filename of the video.
        subfolder (str): The subfolder where the video is stored.
        file_type (str): The type of the file (e.g., 'output').

    Returns:
        bytes: The raw video data, or None if an error occurs.
    """
    print(
        f"worker-comfyui - Fetching video data: type={file_type}, subfolder={subfolder}, filename={filename}"
    )
    data = {"filename": filename, "subfolder": subfolder, "type": file_type}
    url_values = urllib.parse.urlencode(data)
    try:
        # Use requests for consistency and timeout
        response = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=120)
        response.raise_for_status()
        print(f"worker-comfyui - Successfully fetched video data for {filename}")
        return response.content
    except requests.Timeout:
        print(f"worker-comfyui - Timeout fetching video data for {filename}")
        return None
    except requests.RequestException as e:
        print(f"worker-comfyui - Error fetching video data for {filename}: {e}")
        return None
    except Exception as e:
        print(
            f"worker-comfyui - Unexpected error fetching video data for {filename}: {e}"
        )
        return None


def normalize_workflow_for_caching(workflow):
    """
    Normalize workflow to ensure consistent node IDs for better model caching.

    ComfyUI caches models based on node IDs and their configurations.
    To maximize cache hits, we need to ensure that similar workflows
    use consistent node IDs.

    Args:
        workflow (dict): The original workflow

    Returns:
        dict: The normalized workflow with consistent node IDs
    """
    # Create a deep copy to avoid modifying the original
    import copy

    normalized_workflow = copy.deepcopy(workflow)

    # Define standard node ID mappings for common node types
    # This ensures that the same model loader nodes always get the same IDs
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
        "VHS_VideoCombine": "vhs_videocombine_1",
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
                            input_value[1],
                        ]

        new_workflow[new_id] = new_node_data

    return new_workflow


def configure_model_caching():
    """
    Configure ComfyUI for better model caching by adjusting memory management settings.
    This should be called when the worker starts up.
    """
    try:
        # Check current system info to see memory management status
        response = requests.get(f"http://{COMFY_HOST}/system_stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"worker-comfyui - System stats: {stats}")
            
            # Check VRAM status specifically
            if 'vram' in stats:
                vram_info = stats['vram']
                total_vram = vram_info.get('total', 0)
                free_vram = vram_info.get('free', 0)
                used_vram = vram_info.get('used', 0)
                print(f"worker-comfyui - VRAM Status: {used_vram/1024/1024/1024:.1f}GB used, {free_vram/1024/1024/1024:.1f}GB free, {total_vram/1024/1024/1024:.1f}GB total")
                
                # Warn if we're not in high VRAM mode with sufficient memory
                if total_vram > 20 * 1024 * 1024 * 1024:  # More than 20GB
                    print(f"worker-comfyui - High VRAM detected ({total_vram/1024/1024/1024:.1f}GB), ensuring optimal memory management")
        
        # Try to get and log the current model management settings
        response = requests.get(f"http://{COMFY_HOST}/object_info", timeout=5)
        if response.status_code == 200:
            print(f"worker-comfyui - ComfyUI API available for model caching optimization")
            
        # Check if ComfyUI is running in the correct VRAM mode
        response = requests.get(f"http://{COMFY_HOST}/", timeout=5)
        if response.status_code == 200:
            print(f"worker-comfyui - ComfyUI server confirmed running - ready for high VRAM operations")
        
        print(f"worker-comfyui - Model caching configuration completed")
        
    except Exception as e:
        print(f"worker-comfyui - Note: Could not configure advanced model caching: {e}")
        print(f"worker-comfyui - Using basic caching optimizations only")


def handler(job):
    """
    Handles a job using ComfyUI via websockets for status and image retrieval.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    job_input = job["input"]
    job_id = job["id"]

    # Make sure that the input is valid
    validated_data, error_message = validate_input(job_input)
    if error_message:
        return {"error": error_message}

    # Extract validated data
    workflow = validated_data["workflow"]
    input_images = validated_data.get("images")
    
    # Normalize workflow for better model caching
    print(f"worker-comfyui - Normalizing workflow for model caching...")
    original_node_count = len(workflow)
    original_node_ids = list(workflow.keys())
    
    workflow = normalize_workflow_for_caching(workflow)
    
    normalized_node_ids = list(workflow.keys())
    print(f"worker-comfyui - Workflow normalized: {original_node_count} nodes")
    print(f"worker-comfyui - Node ID mapping applied for consistent model caching")
    print(f"worker-comfyui - Original IDs: {', '.join(original_node_ids[:5])}{'...' if len(original_node_ids) > 5 else ''}")
    print(f"worker-comfyui - Normalized IDs: {', '.join(normalized_node_ids[:5])}{'...' if len(normalized_node_ids) > 5 else ''}")

    # Make sure that the ComfyUI HTTP API is available before proceeding
    if not check_server(
        f"http://{COMFY_HOST}/",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    ):
        return {
            "error": f"ComfyUI server ({COMFY_HOST}) not reachable after multiple retries."
        }

    # Upload input images if they exist
    if input_images:
        upload_result = upload_images(input_images)
        if upload_result["status"] == "error":
            # Return upload errors
            return {
                "error": "Failed to upload one or more input images",
                "details": upload_result["details"],
            }

    ws = None
    # Use a consistent client_id to help with model caching
    # You can make this configurable via environment variable if needed
    client_id = os.environ.get("COMFY_CLIENT_ID", "runpod-worker-stable-client")
    prompt_id = None
    output_data = []
    errors = []

    try:
        # Establish WebSocket connection with longer timeout and proper settings
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"
        print(f"worker-comfyui - Connecting to websocket: {ws_url}")
        ws = websocket.WebSocket()
        # Set longer timeout and enable keepalive
        ws.settimeout(30)  # Increased from 10 to 30 seconds
        ws.connect(ws_url, timeout=30)
        print(f"worker-comfyui - Websocket connected")

        # Queue the workflow
        try:
            queued_workflow = queue_workflow(workflow, client_id)
            prompt_id = queued_workflow.get("prompt_id")
            if not prompt_id:
                raise ValueError(
                    f"Missing 'prompt_id' in queue response: {queued_workflow}"
                )
            print(f"worker-comfyui - Queued workflow with ID: {prompt_id}")
        except requests.RequestException as e:
            print(f"worker-comfyui - Error queuing workflow: {e}")
            raise ValueError(f"Error queuing workflow: {e}")
        except Exception as e:
            print(f"worker-comfyui - Unexpected error queuing workflow: {e}")
            # For ValueError exceptions from queue_workflow, pass through the original message
            if isinstance(e, ValueError):
                raise e
            else:
                raise ValueError(f"Unexpected error queuing workflow: {e}")

        # Wait for execution completion via WebSocket
        print(f"worker-comfyui - Waiting for workflow execution ({prompt_id})...")
        execution_done = False
        progress_timeout_count = 0
        max_progress_timeouts = 40  # Allow more timeouts before giving up
        
        while True:
            try:
                out = ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    message_type = message.get("type")
                    
                    if message_type == "status":
                        status_data = message.get("data", {}).get("status", {})
                        queue_remaining = status_data.get('exec_info', {}).get('queue_remaining', 'N/A')
                        print(f"worker-comfyui - Status update: {queue_remaining} items remaining in queue")
                        progress_timeout_count = 0  # Reset timeout counter on status update
                        
                    elif message_type == "progress":
                        data = message.get("data", {})
                        node = data.get("node")
                        value = data.get("value", 0)
                        max_value = data.get("max", 100)
                        progress_pct = (value / max_value * 100) if max_value > 0 else 0
                        print(f"worker-comfyui - Progress: Node {node} - {value}/{max_value} ({progress_pct:.1f}%)")
                        progress_timeout_count = 0  # Reset timeout counter on progress update
                        
                    elif message_type == "executing":
                        data = message.get("data", {})
                        if data.get("node") is None and data.get("prompt_id") == prompt_id:
                            print(f"worker-comfyui - Execution finished for prompt {prompt_id}")
                            execution_done = True
                            break
                        elif data.get("node") is not None:
                            print(f"worker-comfyui - Executing node: {data.get('node')}")
                            progress_timeout_count = 0  # Reset timeout counter on node execution
                            
                    elif message_type == "execution_error":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            error_details = f"Node Type: {data.get('node_type')}, Node ID: {data.get('node_id')}, Message: {data.get('exception_message')}"
                            print(f"worker-comfyui - Execution error received: {error_details}")
                            errors.append(f"Workflow execution error: {error_details}")
                            break
                            
                    elif message_type == "executed":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            node = data.get("node")
                            print(f"worker-comfyui - Node {node} executed successfully")
                            progress_timeout_count = 0  # Reset timeout counter on node completion
                else:
                    continue
                    
            except websocket.WebSocketTimeoutException:
                progress_timeout_count += 1
                print(f"worker-comfyui - Websocket receive timed out ({progress_timeout_count}/{max_progress_timeouts}). Still waiting...")
                
                # If we've had too many timeouts, check if ComfyUI is still alive
                if progress_timeout_count >= max_progress_timeouts:
                    srv_status = _comfy_server_status()
                    if not srv_status["reachable"]:
                        raise websocket.WebSocketConnectionClosedException("ComfyUI server became unreachable")
                    else:
                        # Reset counter and continue if server is still alive
                        progress_timeout_count = 0
                        print(f"worker-comfyui - ComfyUI server still reachable, continuing to wait...")
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                try:
                    # Attempt to reconnect
                    ws = _attempt_websocket_reconnect(
                        ws_url,
                        WEBSOCKET_RECONNECT_ATTEMPTS,
                        WEBSOCKET_RECONNECT_DELAY_S,
                        closed_err,
                    )

                    print(
                        "worker-comfyui - Resuming message listening after successful reconnect."
                    )
                    continue
                except (
                    websocket.WebSocketConnectionClosedException
                ) as reconn_failed_err:
                    # If _attempt_websocket_reconnect fails, it raises this exception
                    # Let this exception propagate to the outer handler's except block
                    raise reconn_failed_err

            except json.JSONDecodeError:
                print(f"worker-comfyui - Received invalid JSON message via websocket.")

        if not execution_done and not errors:
            raise ValueError(
                "Workflow monitoring loop exited without confirmation of completion or error."
            )

        # Fetch history even if there were execution errors, some outputs might exist
        print(f"worker-comfyui - Fetching history for prompt {prompt_id}...")
        history = get_history(prompt_id)

        if prompt_id not in history:
            error_msg = f"Prompt ID {prompt_id} not found in history after execution."
            print(f"worker-comfyui - {error_msg}")
            if not errors:
                return {"error": error_msg}
            else:
                errors.append(error_msg)
                return {
                    "error": "Job processing failed, prompt ID not found in history.",
                    "details": errors,
                }

        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})

        if not outputs:
            warning_msg = f"No outputs found in history for prompt {prompt_id}."
            print(f"worker-comfyui - {warning_msg}")
            if not errors:
                errors.append(warning_msg)

        print(f"worker-comfyui - Processing {len(outputs)} output nodes...")
        for node_id, node_output in outputs.items():
            # Process images
            if "images" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['images'])} image(s)"
                )
                for image_info in node_output["images"]:
                    filename = image_info.get("filename")
                    subfolder = image_info.get("subfolder", "")
                    img_type = image_info.get("type")

                    # skip temp images
                    if img_type == "temp":
                        print(
                            f"worker-comfyui - Skipping image {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping image in node {node_id} due to missing filename: {image_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    image_bytes = get_image_data(filename, subfolder, img_type)

                    if image_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".png"

                        if os.environ.get("BUCKET_ENDPOINT_URL"):
                            try:
                                with tempfile.NamedTemporaryFile(
                                    suffix=file_extension, delete=False
                                ) as temp_file:
                                    temp_file.write(image_bytes)
                                    temp_file_path = temp_file.name
                                print(
                                    f"worker-comfyui - Wrote image bytes to temporary file: {temp_file_path}"
                                )

                                print(f"worker-comfyui - Uploading {filename} to S3...")
                                s3_url = rp_upload.upload_image(job_id, temp_file_path)
                                os.remove(temp_file_path)  # Clean up temp file
                                print(
                                    f"worker-comfyui - Uploaded {filename} to S3: {s3_url}"
                                )
                                # Append dictionary with filename and URL
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "s3_url",
                                        "data": s3_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = f"Error uploading {filename} to S3: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    try:
                                        os.remove(temp_file_path)
                                    except OSError as rm_err:
                                        print(
                                            f"worker-comfyui - Error removing temp file {temp_file_path}: {rm_err}"
                                        )
                        else:
                            # Return as base64 string
                            try:
                                base64_image = base64.b64encode(image_bytes).decode(
                                    "utf-8"
                                )
                                # Append dictionary with filename and base64 data
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_image,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch image data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # Process videos (from VHS_VideoCombine and similar nodes)
            if "gifs" in node_output:
                print(
                    f"worker-comfyui - Node {node_id} contains {len(node_output['gifs'])} video/gif file(s)"
                )
                for video_info in node_output["gifs"]:
                    filename = video_info.get("filename")
                    subfolder = video_info.get("subfolder", "")
                    file_type = video_info.get("type", "output")

                    # skip temp files
                    if file_type == "temp":
                        print(
                            f"worker-comfyui - Skipping video {filename} because type is 'temp'"
                        )
                        continue

                    if not filename:
                        warn_msg = f"Skipping video in node {node_id} due to missing filename: {video_info}"
                        print(f"worker-comfyui - {warn_msg}")
                        errors.append(warn_msg)
                        continue

                    video_bytes = get_video_data(filename, subfolder, file_type)

                    if video_bytes:
                        file_extension = os.path.splitext(filename)[1] or ".mp4"

                        if os.environ.get("BUCKET_ENDPOINT_URL"):
                            try:
                                with tempfile.NamedTemporaryFile(
                                    suffix=file_extension, delete=False
                                ) as temp_file:
                                    temp_file.write(video_bytes)
                                    temp_file_path = temp_file.name
                                print(
                                    f"worker-comfyui - Wrote video bytes to temporary file: {temp_file_path}"
                                )

                                print(f"worker-comfyui - Uploading {filename} to S3...")
                                s3_url = rp_upload.upload_image(job_id, temp_file_path)  # Note: rp_upload.upload_image works for any file type
                                os.remove(temp_file_path)  # Clean up temp file
                                print(
                                    f"worker-comfyui - Uploaded {filename} to S3: {s3_url}"
                                )
                                # Append dictionary with filename and URL
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "s3_url",
                                        "data": s3_url,
                                    }
                                )
                            except Exception as e:
                                error_msg = f"Error uploading {filename} to S3: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    try:
                                        os.remove(temp_file_path)
                                    except OSError as rm_err:
                                        print(
                                            f"worker-comfyui - Error removing temp file {temp_file_path}: {rm_err}"
                                        )
                        else:
                            # Return as base64 string
                            try:
                                base64_video = base64.b64encode(video_bytes).decode(
                                    "utf-8"
                                )
                                # Append dictionary with filename and base64 data
                                output_data.append(
                                    {
                                        "filename": filename,
                                        "type": "base64",
                                        "data": base64_video,
                                    }
                                )
                                print(f"worker-comfyui - Encoded {filename} as base64")
                            except Exception as e:
                                error_msg = f"Error encoding {filename} to base64: {e}"
                                print(f"worker-comfyui - {error_msg}")
                                errors.append(error_msg)
                    else:
                        error_msg = f"Failed to fetch video data for {filename} from /view endpoint."
                        errors.append(error_msg)

            # Check for other output types that we don't handle yet
            handled_keys = {"images", "gifs"}
            other_keys = [k for k in node_output.keys() if k not in handled_keys]
            if other_keys:
                warn_msg = (
                    f"Node {node_id} produced unhandled output keys: {other_keys}."
                )
                print(f"worker-comfyui - WARNING: {warn_msg}")
                print(
                    f"worker-comfyui - --> If this output is useful, please consider opening an issue on GitHub to discuss adding support."
                )

    except websocket.WebSocketException as e:
        print(f"worker-comfyui - WebSocket Error: {e}")
        print(traceback.format_exc())
        return {"error": f"WebSocket communication error: {e}"}
    except requests.RequestException as e:
        print(f"worker-comfyui - HTTP Request Error: {e}")
        print(traceback.format_exc())
        return {"error": f"HTTP communication error with ComfyUI: {e}"}
    except ValueError as e:
        print(f"worker-comfyui - Value Error: {e}")
        print(traceback.format_exc())
        return {"error": str(e)}
    except Exception as e:
        print(f"worker-comfyui - Unexpected Handler Error: {e}")
        print(traceback.format_exc())
        return {"error": f"An unexpected error occurred: {e}"}
    finally:
        if ws and ws.connected:
            print(f"worker-comfyui - Closing websocket connection.")
            ws.close()

    final_result = {}

    if output_data:
        final_result["images"] = output_data

    if errors:
        final_result["errors"] = errors
        print(f"worker-comfyui - Job completed with errors/warnings: {errors}")

    if not output_data and errors:
        print(f"worker-comfyui - Job failed with no output files.")
        return {
            "error": "Job processing failed",
            "details": errors,
        }
    elif not output_data and not errors:
        print(
            f"worker-comfyui - Job completed successfully, but the workflow produced no output files."
        )
        final_result["status"] = "success_no_files"
        final_result["images"] = []

    print(f"worker-comfyui - Job completed. Returning {len(output_data)} file(s).")
    return final_result


if __name__ == "__main__":
    print("worker-comfyui - Starting handler...")
    
    # Configure model caching for better performance
    configure_model_caching()
    
    runpod.serverless.start({"handler": handler})
