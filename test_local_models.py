#!/usr/bin/env python3
"""
Test script for local model integration in DGM.
This script tests different local model configurations.
"""

import os
import sys
from llm import create_client, get_response_from_llm, AVAILABLE_LLMS

def test_local_model(model_name):
    """Test a specific local model configuration."""
    print(f"\n\n=== Testing {model_name} ===")
    
    try:
        # Create client for the model
        client = create_client(model_name)
        print(f"✓ Successfully created client for {model_name}")
        
        # Test simple completion
        messages = [{"role": "user", "content": "Say hello and introduce yourself in one sentence."}]
        response = get_response_from_llm(client, messages, model_name)
        
        print(f"✓ Got response from {model_name}:")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"✗ Error with {model_name}: {str(e)}")
        return False

def main():
    """Main test function."""
    print("Available models:")
    for model in AVAILABLE_LLMS:
        print(f"- {model}")
    
    print("\nTesting local models...")
    
    # Test Hugging Face model if environment is set up
    if os.environ.get("HUGGINGFACE_HUB_TOKEN") or not os.environ.get("HF_REQUIRE_TOKEN", "false").lower() == "true":
        test_local_model("hf/TheBloke/Llama-3.1-8B-Instruct-GGUF")
    
    # Test llama.cpp if model path is set
    if os.environ.get("LLAMA_CPP_MODEL_PATH"):
        test_local_model("llama.cpp")
    
    # Test Ollama if base URL is set
    if os.environ.get("OLLAMA_BASE_URL"):
        test_local_model("ollama/llama3")
    
    # Test LocalAI if base URL is set
    if os.environ.get("LOCALAI_BASE_URL"):
        test_local_model("localai/llama3")

    # Test GGUF model discovery if directory is set
    if os.environ.get("GGUF_MODEL_DIR"):
        # Assuming a model named 'my-gguf-model.gguf' exists in GGUF_MODEL_DIR
        test_local_model("my-gguf-model")
    
    print("\nTest completed!")

if __name__ == "__main__":
    main()