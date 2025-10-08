#!/usr/bin/env python3

import os
import sys
import argparse

# Add the parent directory to the Python path to allow imports from the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm import create_client

def main():
    parser = argparse.ArgumentParser(description="Select and run an LLM provider.")
    parser.add_argument("--provider", type=str, choices=["openai", "huggingface", "local"], required=True,
                        help="Choose an LLM provider: openai, huggingface, or local.")
    parser.add_argument("--model", type=str, required=True,
                        help="Specify the model name or path based on the provider.")
    parser.add_argument("--filename", type=str, default=None,
                        help="Optional filename for Hugging Face models.")
    
    args = parser.parse_args()

    model_name = ""
    if args.provider == "openai":
        model_name = args.model
    elif args.provider == "huggingface":
        if args.filename:
            model_name = f"hf/{args.model}/{args.filename}"
        else:
            model_name = f"hf/{args.model}"
    elif args.provider == "local":
        model_name = f"local/{args.model}"

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