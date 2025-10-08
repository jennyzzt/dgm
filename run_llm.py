#!/usr/bin/env python3

import os
import sys

# Add the parent directory to the Python path to allow imports from the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm import create_client

def main():
    print("Select an LLM provider:")
    print("1. OpenAI (requires OPENAI_API_KEY environment variable)")
    print("2. Hugging Face (requires HF_TOKEN environment variable for private/gated models)")
    print("3. Local GGUF Model")

    choice = input("Enter your choice (1-3): ")

    model_name = ""
    if choice == "1":
        model_name = input("Enter OpenAI model name (e.g., gpt-4o): ")
    elif choice == "2":
        repo_id = input("Enter Hugging Face repo ID (e.g., TheBloke/Llama-3.1-8B-Instruct-GGUF): ")
        filename = input("Enter optional filename (leave blank to auto-detect): ")
        if filename:
            model_name = f"hf/{repo_id}/{filename}"
        else:
            model_name = f"hf/{repo_id}"
    elif choice == "3":
        model_path = input("Enter path to local GGUF model file or directory: ")
        model_name = f"local/{model_path}"
    else:
        print("Invalid choice.")
        sys.exit(1)

    try:
        client, _ = create_client(model_name)
        print(f"Successfully created client for model: {model_name}")
        # You can now use the 'client' object to interact with the LLM
        # For example:
        # response = client.chat.completions.create(
        #     model=model_name, # Note: for OpenAI, model_name is used here
        #     messages=[{"role": "user", "content": "Hello, how are you?"}]
        # )
        # print(response.choices[0].message.content)

    except Exception as e:
        print(f"Error creating client: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()