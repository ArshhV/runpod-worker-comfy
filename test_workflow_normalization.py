#!/usr/bin/env python3
"""
Test script to verify workflow normalization is working correctly.
This helps ensure consistent node IDs for better model caching.
"""

import json
from pathlib import Path

def normalize_workflow_node_ids(workflow):
    """
    Normalize workflow node IDs to ensure consistent caching between requests.
    """
    import copy
    
    # Create a deep copy to avoid modifying the original
    normalized_workflow = copy.deepcopy(workflow)
    
    # Define standard node ID mappings for common node types
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
        "SaveAnimatedWEBP": "save_webp_1"
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

def test_normalization():
    """Test the workflow normalization function."""
    
    # Load the original workflow
    workflow_path = Path(__file__).parent / "wanLatest.json"
    
    if not workflow_path.exists():
        print(f"❌ Workflow file not found: {workflow_path}")
        return False
    
    try:
        with open(workflow_path, 'r') as f:
            original_workflow = json.load(f)
    except Exception as e:
        print(f"❌ Error loading workflow: {e}")
        return False
    
    print("🔍 Testing workflow normalization...")
    print(f"📊 Original workflow has {len(original_workflow)} nodes")
    
    # Show original node IDs
    print("\n📋 Original node IDs:")
    for node_id, node_data in original_workflow.items():
        class_type = node_data.get("class_type", "unknown")
        print(f"  {node_id}: {class_type}")
    
    # Normalize the workflow
    normalized_workflow = normalize_workflow_node_ids(original_workflow)
    
    print(f"\n✅ Normalized workflow has {len(normalized_workflow)} nodes")
    
    # Show normalized node IDs
    print("\n📋 Normalized node IDs:")
    for node_id, node_data in normalized_workflow.items():
        class_type = node_data.get("class_type", "unknown")
        print(f"  {node_id}: {class_type}")
    
    # Test consistency - normalize the same workflow again
    normalized_again = normalize_workflow_node_ids(original_workflow)
    
    if normalized_workflow == normalized_again:
        print("\n✅ Normalization is consistent - same input produces same output")
    else:
        print("\n❌ Normalization is NOT consistent - this could cause model reloading!")
        return False
    
    # Save normalized workflow for inspection
    output_path = Path(__file__).parent / "wanLatest_normalized.json"
    try:
        with open(output_path, 'w') as f:
            json.dump(normalized_workflow, f, indent=2)
        print(f"💾 Normalized workflow saved to: {output_path}")
    except Exception as e:
        print(f"⚠️  Could not save normalized workflow: {e}")
    
    # Verify that all references are correctly updated
    print("\n🔍 Verifying node references...")
    reference_errors = []
    
    for node_id, node_data in normalized_workflow.items():
        if "inputs" in node_data:
            for input_key, input_value in node_data["inputs"].items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    referenced_node_id = str(input_value[0])
                    if referenced_node_id not in normalized_workflow:
                        reference_errors.append(
                            f"Node {node_id} references non-existent node {referenced_node_id} in input {input_key}"
                        )
    
    if reference_errors:
        print("❌ Reference errors found:")
        for error in reference_errors:
            print(f"  • {error}")
        return False
    else:
        print("✅ All node references are valid")
    
    print("\n🎉 Workflow normalization test completed successfully!")
    print("📈 This should help prevent model reloading between requests")
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Workflow Normalization Test")
    print("=" * 60)
    
    success = test_normalization()
    
    if success:
        print("\n✅ All tests passed! Workflow normalization is working correctly.")
        exit(0)
    else:
        print("\n❌ Tests failed! Please check the normalization logic.")
        exit(1)
