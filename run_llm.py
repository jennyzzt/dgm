#!/usr/bin/env python3

import os
import sys
import re
import argparse

# Add the parent directory to the Python path to allow imports from the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm import create_client

def _is_pathlike(s: str) -> bool:
    if not s:
        return False
    if os.path.isabs(s):
        return True
    if s.endswith('.gguf'):
        return True
    if os.sep in s or ('/' in s) or ('\\' in s):
        return True
    if sys.platform.startswith('win') and re.match(r'^[A-Za-z]:\\', s):
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Select and run an LLM provider.")
    parser.add_argument(
        "--provider",
        type=str,
        choices=[
            "openai",
            "anthropic",
            "bedrock",
            "vertex_ai",
            "deepseek",
            "openrouter",
            "ollama",
            "localai",
            "llama-cpp",
            "huggingface",
            "local",
        ],
        required=True,
        help=(
            "Choose an LLM provider: openai, anthropic, bedrock, vertex_ai, deepseek, openrouter, "
            "ollama, localai, llama-cpp, huggingface, or local."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Specify the model name or path based on the provider. Required unless --provider is 'local' and --model_dir is used.",
    )
    parser.add_argument(
        "--model_dir",
        type=str,
        default=None,
        help="Directory to search for GGUF models when --provider is 'local'.",
    )
    parser.add_argument("--filename", type=str, default=None, help="Optional filename for Hugging Face models.")

    args = parser.parse_args()

    # Default local GGUF discovery directory: repo_root/local_models (can be overridden by GGUF_MODEL_DIR)
    repo_root = os.path.dirname(os.path.abspath(__file__))
    default_local_models_dir = os.path.join(repo_root, "local_models")
    os.environ.setdefault("GGUF_MODEL_DIR", default_local_models_dir)

    provider = args.provider
    model_name = ""

    if provider == "openai":
        # e.g., gpt-4o-2024-05-13, o1-mini-2024-09-12, o3-mini-2025-01-31
        model_name = args.model
    elif provider == "anthropic":
        # e.g., claude-3-5-sonnet-20241022
        model_name = args.model
    elif provider == "bedrock":
        # e.g., anthropic.claude-3-5-sonnet-20241022-v2:0
        model_name = args.model if args.model.startswith("bedrock/") else f"bedrock/{args.model}"
    elif provider == "vertex_ai":
        # e.g., claude-3-5-sonnet-v2@20241022
        model_name = args.model if args.model.startswith("vertex_ai/") else f"vertex_ai/{args.model}"
    elif provider == "deepseek":
        # deepseek-chat, deepseek-coder, deepseek-reasoner
        model_name = args.model
    elif provider == "openrouter":
        # Current codebase supports openrouter via special cases (e.g., llama3.1-405b)
        model_name = args.model
    elif provider == "ollama":
        # e.g., ollama/llama3.2
        model_name = args.model if args.model.startswith("ollama/") else f"ollama/{args.model}"
    elif provider == "localai":
        # e.g., localai/llama3
        model_name = args.model if args.model.startswith("localai/") else f"localai/{args.model}"
    elif provider == "llama-cpp":
        # If a path-like is provided, use llama-cpp/<absolute_or_relative_path_to_gguf>
        # Otherwise, fall back to GGUF discovery by passing the bare name (will be resolved via GGUF_MODEL_DIR)
        if _is_pathlike(args.model):
            model_name = f"llama-cpp/{args.model}"
        else:
            # Let discovery find it by name
            model_name = args.model
    elif provider == "huggingface":
        # Constructs hf/<repo_id>[/filename]
        if args.filename:
            model_name = f"hf/{args.model}/{args.filename}"
        else:
            model_name = f"hf/{args.model}"
    elif provider == "local":
        if args.model_dir:
            if not os.path.isdir(args.model_dir):
                print(f"Error: Model directory not found at {args.model_dir}")
                sys.exit(1)
            
            gguf_files = [f for f in os.listdir(args.model_dir) if f.endswith(".gguf")]
            if not gguf_files:
                print(f"No GGUF files found in {args.model_dir}")
                sys.exit(1)
            
            if args.model:
                # If a specific model is provided, check if it exists in the directory
                if args.model not in gguf_files:
                    print(f"Error: Specified model {args.model} not found in {args.model_dir}")
                    sys.exit(1)
                model_name = f"local/{os.path.join(args.model_dir, args.model)}"
            else:
                # If no specific model is provided, list them for interactive selection
                print(f"Found GGUF models in {args.model_dir}:")
                for i, file in enumerate(gguf_files):
                    print(f"{i + 1}. {file}")
                
                while True:
                    try:
                        selection = input("Select a model by number: ")
                        index = int(selection) - 1
                        if 0 <= index < len(gguf_files):
                            selected_file = gguf_files[index]
                            model_name = f"local/{os.path.join(args.model_dir, selected_file)}"
                            break
                        else:
                            print("Invalid selection. Please enter a valid number.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
        elif args.model:
            # If a path-like is provided, use local/<path or dir>. If a plain name is provided,
            # let GGUF discovery find it via GGUF_MODEL_DIR by passing the bare name.
            if _is_pathlike(args.model):
                model_name = f"local/{args.model}"
            else:
                model_name = args.model
        else:
            print("Error: For local provider, either --model or --model_dir must be specified.")
            sys.exit(1)

    try:
        client, resolved_model = create_client(model_name)
        print(f"Successfully created client for model: {model_name} (resolved: {resolved_model})")
        # Example usage (commented):
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[{"role": "user", "content": "Tell me a short story about a robot."}],
        )
        print(response.choices[0].message.content)

    except Exception as e:
        print(f"Error creating client: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
