# Code adapted from https://github.com/SakanaAI/AI-Scientist/blob/main/ai_scientist/llm.py.
import json
import os
import re
from types import SimpleNamespace

import anthropic
import backoff
import openai
MAX_OUTPUT_TOKENS = 2048

AVAILABLE_LLMS = [
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "o1-preview-2024-09-12",
    "o1-mini-2024-09-12",
    "o1-2024-12-17",
    "o3-mini-2025-01-31",
    # OpenRouter models
    "llama3.1-405b",
    # Anthropic Claude models via Amazon Bedrock
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    "bedrock/us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    # Anthropic Claude models Vertex AI
    "vertex_ai/claude-3-opus@20240229",
    "vertex_ai/claude-3-5-sonnet@20240620",
    "vertex_ai/claude-3-5-sonnet-v2@20241022",
    "vertex_ai/claude-3-sonnet@20240229",
    "vertex_ai/claude-3-haiku@20240307",
    # DeepSeek models
    "deepseek-chat",
    "deepseek-coder",
    "deepseek-reasoner",
    "ollama/llama3.2",
    "ollama/llama3.1",
]

# Optional local model runtimes
try:
    from llama_cpp import Llama
except Exception:
    Llama = None

try:
    import huggingface_hub
except ImportError:
    huggingface_hub = None

def find_gguf_models(search_dir: str) -> dict[str, str]:
    """
    Searches a directory for GGUF model files and returns a dictionary
    mapping model names (filenames without .gguf extension) to their full paths.
    """
    found_models = {}
    if not os.path.isdir(search_dir):
        print(f"Warning: GGUF search directory '{search_dir}' does not exist.")
        return found_models

    for root, _, files in os.walk(search_dir):
        for file in files:
            if file.endswith(".gguf"):
                model_path = os.path.join(root, file)
                model_name = os.path.splitext(file)[0]
                found_models[model_name] = model_path
    return found_models

    "ollama/llama3.2",
    "ollama/llama3.1",
    "ollama/codellama",
    "ollama/mistral",
    # LocalAI models (examples; users can specify any LocalAI model as localai/<model_name>)
    "localai/llama-3.2-3b-instruct",
    "localai/llama-3.1-8b-instruct",
    "localai/mistral-7b-instruct",
    # Hugging Face models (examples; users can specify any HF model as hf/<repo_id>)
    "hf/TheBloke/Llama-3.1-8B-Instruct-GGUF",
    "hf/TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
    "hf/TheBloke/Phi-3-mini-4k-instruct-GGUF",
    # Local file models via llama.cpp (examples)
    # Use DGM_MODEL='llama-cpp/<absolute_path_to_model.gguf>' or set LLAMA_CPP_MODEL_PATH
    "llama-cpp",


class LocalModelClient:
    """Base class for local model clients that provide OpenAI-compatible interfaces."""
    
    def __init__(self):
        self._openai_compatible_chat = SimpleNamespace()
        self._openai_compatible_chat.completions = SimpleNamespace()
        self._openai_compatible_chat.completions.create = self._create_completion
    
    @property
    def chat(self):
        return self._openai_compatible_chat
    
    def _create_completion(self, **kwargs):
        """To be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _create_completion")
    
    def _format_response(self, content):
        """Format response to match OpenAI API response structure."""
        response = SimpleNamespace()
        response.choices = [SimpleNamespace()]
        response.choices[0].message = SimpleNamespace()
        response.choices[0].message.content = content
        return response

class LlamaCppChatClient(LocalModelClient):
    """Minimal OpenAI-compatible chat client backed by llama.cpp (local GGUF files).

    It exposes client.chat.completions.create(...), returning an object with
    .choices[0].message.content to match the OpenAI client usage in this codebase.
    """

    def __init__(self, model_path: str, n_ctx: int = 8192, n_gpu_layers: int = 0, chat_format: str = "llama-3"):
        super().__init__()
        if Llama is None:
            raise ImportError(
                "llama-cpp-python is not installed. Install with: pip install llama-cpp-python"
            )
        # Initialize llama.cpp
        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            chat_format=chat_format,
        )
        
    def _create_completion(self, model, messages, temperature=0.7, max_tokens=MAX_OUTPUT_TOKENS, **kwargs):
        """Create a chat completion using llama.cpp."""
        # Format messages for llama.cpp
        formatted_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle content that might be a list of content blocks
                content = " ".join([c.get("text", "") if isinstance(c, dict) else c for c in content])
            formatted_messages.append({"role": role, "content": content})
        
        # Generate completion
        completion = self._llm.create_chat_completion(
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return completion

class HuggingFaceChatClient(LocalModelClient):
    """OpenAI-compatible chat client for Hugging Face models.
    
    Downloads models from Hugging Face Hub and uses llama.cpp to run them.
    """
    
    def __init__(self, repo_id: str, filename: str = None, n_ctx: int = 8192, n_gpu_layers: int = 0, chat_format: str = "llama-3"):
        super().__init__()
        if huggingface_hub is None:
            raise ImportError(
                "huggingface_hub is not installed. Install with: pip install huggingface_hub"
            )
        if Llama is None:
            raise ImportError(
                "llama-cpp-python is not installed. Install with: pip install llama-cpp-python"
            )
            
        # Download model from Hugging Face
        print(f"Downloading model from Hugging Face: {repo_id}")
        if filename:
            model_path = huggingface_hub.hf_hub_download(repo_id=repo_id, filename=filename)
        else:
            # Try to find a GGUF file in the repo
            files = huggingface_hub.list_repo_files(repo_id=repo_id)
            gguf_files = [f for f in files if f.endswith(".gguf")]
            if not gguf_files:
                raise ValueError(f"No GGUF files found in repository {repo_id}")
            
            # Prefer smaller quantized models (Q4_K_M, Q5_K_M) if available
            preferred_quantizations = ["Q4_K_M", "Q5_K_M", "Q4_0", "Q5_0", "Q8_0"]
            for quant in preferred_quantizations:
                for file in gguf_files:
                    if quant in file:
                        filename = file
                        break
                if filename:
                    break
            
            # If no preferred quantization found, use the first GGUF file
            if not filename:
                filename = gguf_files[0]
                
            model_path = huggingface_hub.hf_hub_download(repo_id=repo_id, filename=filename)
        
        print(f"Model downloaded to: {model_path}")
        
        # Initialize llama.cpp with the downloaded model
        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            chat_format=chat_format,
        )
    
    def _create_completion(self, model, messages, temperature=0.7, max_tokens=MAX_OUTPUT_TOKENS, **kwargs):
        """Create a chat completion using the Hugging Face model via llama.cpp."""
        # Format messages for llama.cpp
        formatted_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle content that might be a list of content blocks
                content = " ".join([c.get("text", "") if isinstance(c, dict) else c for c in content])
            formatted_messages.append({"role": role, "content": content})
        
        # Generate completion
        completion = self._llm.create_chat_completion(
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return completion

    class _Completions:
        def __init__(self, parent: "LlamaCppChatClient"):
            self._parent = parent

        def create(self, model=None, messages=None, temperature=0.7, max_tokens=MAX_OUTPUT_TOKENS, n=1, stop=None, seed=None, **kwargs):
            if messages is None:
                messages = []
            args = dict(messages=messages, temperature=float(temperature), max_tokens=int(max_tokens))
            if stop:
                args["stop"] = stop
            # llama-cpp create_chat_completion accepts the OpenAI messages format
            resp = self._parent._llm.create_chat_completion(**args)
            # Normalize into an object with .choices[0].message.content
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    class _Chat:
        def __init__(self, parent: "LlamaCppChatClient"):
            self.completions = LlamaCppChatClient._Completions(parent)

    @property
    def chat(self):
        return LlamaCppChatClient._Chat(self)


def create_client(model: str):
    """
    Create and return an LLM client based on the specified model.
    Args:
        model (str): The name of the model to use.
    Returns:
        Tuple[Any, str]: A tuple containing the client instance and the client model name.
    """
    # Cloud API models
    if model.startswith("claude-"):
        print(f"Using Anthropic API with model {model}.")
        return anthropic.Anthropic(), model
    elif model.startswith("bedrock") and "claude" in model:
        client_model = model.split("/")[-1]
        print(f"Using Amazon Bedrock with model {client_model}.")
        client = anthropic.AnthropicBedrock(
            aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region=os.getenv("AWS_REGION_NAME"),
        )
        return client, client_model
    elif model.startswith("vertex_ai") and "claude" in model:
        client_model = model.split("/")[-1]
        print(f"Using Vertex AI with model {client_model}.")
        return anthropic.AnthropicVertex(), client_model
    elif 'gpt' in model or model.startswith("o1-") or model.startswith("o3-"):
        print(f"Using OpenAI API with model {model}.")
        return openai.OpenAI(), model
    elif model.startswith("deepseek-"):
        print(f"Using OpenAI API with {model}.")
        client = openai.OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        return client, model
    elif model == "llama3.1-405b":
        print(f"Using OpenAI API with {model}.")
        client = openai.OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
        return client, model
    
    # Local API models (Ollama, LocalAI)
    elif model.startswith("ollama/"):
        client_model = model.split("/", 1)[1]
        print(f"Using Ollama with model {client_model}.")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        return client, client_model
    elif model.startswith("localai/"):
        client_model = model.split("/", 1)[1]
        print(f"Using LocalAI with model {client_model}.")
        base_url = os.getenv("LOCALAI_BASE_URL", "http://localhost:8080/v1")
        api_key = os.getenv("LOCALAI_API_KEY", "localai")
        client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        return client, client_model
    
    # Direct local model loading
    elif model.startswith("llama-cpp"):
        # Format: 'llama-cpp/<absolute_path_to_model.gguf>' or set LLAMA_CPP_MODEL_PATH
        model_path = model[len("llama-cpp/"):] if len(model) > len("llama-cpp/") else os.getenv("LLAMA_CPP_MODEL_PATH")
        if not model_path:
            raise ValueError("llama-cpp model path not provided. Set DGM_MODEL='llama-cpp/<absolute_path_to_gguf>' or LLAMA_CPP_MODEL_PATH env var.")
        n_ctx = int(os.getenv("LLAMA_CPP_N_CTX", "8192"))
        n_gpu_layers = int(os.getenv("LLAMA_CPP_N_GPU_LAYERS", "0"))
        chat_format = os.getenv("LLAMA_CPP_CHAT_FORMAT", "llama-3")
        print(f"Using llama-cpp local model at {model_path} (ctx={n_ctx}, gpu_layers={n_gpu_layers}, chat_format={chat_format}).")
        client = LlamaCppChatClient(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, chat_format=chat_format)
        # For llama-cpp we return the model string as-is; downstream uses it only for routing
        return client, model
    elif model.startswith("hf/"):
        # Remove "hf/" prefix
        hf_path = model[len("hf/"):]
        
        parts = hf_path.split('/')
        
        repo_id_full = hf_path
        filename = None

        # If the last part contains a dot, assume it's a filename
        if len(parts) > 1 and '.' in parts[-1]:
            filename = parts[-1]
            repo_id_full = '/'.join(parts[:-1])

        if not repo_id_full:
            raise ValueError(f"Invalid Hugging Face model format: {model}. Expected hf/owner/repo or hf/owner/repo/filename")

        print(f"Using Hugging Face model {repo_id_full} (filename: {filename}).")
        n_ctx = int(os.getenv("LLAMA_CPP_N_CTX", "8192"))
        n_gpu_layers = int(os.getenv("LLAMA_CPP_N_GPU_LAYERS", "0"))
        chat_format = os.getenv("LLAMA_CPP_CHAT_FORMAT", "llama-3")
        client = HuggingFaceChatClient(repo_id=repo_id_full, filename=filename, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, chat_format=chat_format)
        return client, model
    else:
        # Try to find a GGUF model in the local directory
        gguf_search_dir = os.environ.get("GGUF_MODEL_DIR")
        if gguf_search_dir:
            found_models = find_gguf_models(gguf_search_dir)
            if model in found_models:
                model_path = found_models[model]
                print(f"Found local GGUF model '{model}' at {model_path}")
                n_ctx = int(os.getenv("LLAMA_CPP_N_CTX", "8192"))
                n_gpu_layers = int(os.getenv("LLAMA_CPP_N_GPU_LAYERS", "0"))
                chat_format = os.getenv("LLAMA_CPP_CHAT_FORMAT", "llama-3")
                client = LlamaCppChatClient(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, chat_format=chat_format)
                return client, model
            else:
                print(f"Local GGUF model '{model}' not found in '{gguf_search_dir}'.")
        raise ValueError(f"Model {model} not supported.")

# Get N responses from a single message, used for ensembling.
@backoff.on_exception(backoff.expo, (openai.RateLimitError, openai.APITimeoutError))
def get_batch_responses_from_llm(
        msg,
        client,
        model,
        system_message,
        print_debug=False,
        msg_history=None,
        temperature=0.75,
        n_responses=1,
):
    if msg_history is None:
        msg_history = []

    if model in [
        "gpt-4o-2024-05-13",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-2024-08-06",
    ]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=n_responses,
            stop=None,
            seed=0,
        )
        content = [r.message.content for r in response.choices]
        new_msg_history = [
            new_msg_history + [{"role": "assistant", "content": c}] for c in content
        ]
    elif model == "llama-3-1-405b-instruct":
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-405b-instruct",
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=n_responses,
            stop=None,
        )
        content = [r.message.content for r in response.choices]
        new_msg_history = [
            new_msg_history + [{"role": "assistant", "content": c}] for c in content
        ]
    else:
        content, new_msg_history = [], []
        for _ in range(n_responses):
            c, hist = get_response_from_llm(
                msg,
                client,
                model,
                system_message,
                print_debug=False,
                msg_history=None,
                temperature=temperature,
            )
            content.append(c)
            new_msg_history.append(hist)

    if print_debug:
        print()
        print("*" * 20 + " LLM START " + "*" * 20)
        for j, msg in enumerate(new_msg_history[0]):
            print(f'{j}, {msg["role"]}: {msg["content"]}')
        print(content)
        print("*" * 21 + " LLM END " + "*" * 21)
        print()

    return content, new_msg_history

@backoff.on_exception(
    backoff.expo,
    (openai.RateLimitError, openai.APITimeoutError, anthropic.RateLimitError, anthropic.APIStatusError),
    max_time=120,
)
def get_response_from_llm(
        msg,
        client,
        model,
        system_message,
        print_debug=False,
        msg_history=None,
        temperature=0.7,
):
    if msg_history is None:
        msg_history = []

    if "claude" in model:
        new_msg_history = msg_history + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": msg,
                    }
                ],
            }
        ]
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=temperature,
            system=system_message,
            messages=new_msg_history,
        )
        content = response.content[0].text
        new_msg_history = new_msg_history + [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": content,
                    }
                ],
            }
        ]
    elif model.startswith("gpt-4o-"):
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=1,
            stop=None,
            seed=0,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model.startswith("o1-") or model.startswith("o3-"):
        new_msg_history = msg_history + [{"role": "user", "content": system_message + msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                # {"role": "user", "content": system_message},
                *new_msg_history,
            ],
            temperature=1,
            # max_completion_tokens=MAX_OUTPUT_TOKENS,
            n=1,
            # stop=None,
            seed=0,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model in ["deepseek-chat", "deepseek-coder"]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    elif model in ["deepseek-reasoner"]:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        reasoning_content = response.choices[0].message.reasoning_content
    elif model.startswith("llama3.1-"):
        llama_size = model.split("-")[-1]
        client_model = f"meta-llama/llama-3.1-{llama_size}-instruct"
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=client_model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
        resoning_content = response.choices[0].message.reasoning_content
    else:
        # General OpenAI-compatible handling (e.g., Ollama, LocalAI, llama-cpp wrapper)
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
    if print_debug:
        print()
        print("*" * 20 + " LLM START " + "*" * 20)
        print(f'User: {new_msg_history[-2]["content"]}')
        print(f'Assistant: {new_msg_history[-1]["content"]}')
        print("*" * 21 + " LLM END " + "*" * 21)
        print()
    return content, new_msg_history

def extract_json_between_markers(llm_output):
    inside_json_block = False
    json_lines = []
    
    # Split the output into lines and iterate
    for line in llm_output.split('\n'):
        striped_line = line.strip()
        
        # Check for start of JSON code block
        if striped_line.startswith("```json"):
            inside_json_block = True
            continue
        
        # Check for end of code block
        if inside_json_block and striped_line.startswith("```"):
            # We've reached the closing triple backticks.
            inside_json_block = False
            break
        
        # If we're inside the JSON block, collect the lines
        if inside_json_block:
            json_lines.append(line)
    
    # If we never found a JSON code block, fallback to any JSON-like content
    if not json_lines:
        # Fallback: Try a regex that finds any JSON-like object in the text
        fallback_pattern = r"\{.*?\}"
        matches = re.findall(fallback_pattern, llm_output, re.DOTALL)
        for candidate in matches:
            candidate = candidate.strip()
            if candidate:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Attempt to clean control characters and re-try
                    candidate_clean = re.sub(r"[\x00-\x1F\x7F]", "", candidate)
                    try:
                        return json.loads(candidate_clean)
                    except json.JSONDecodeError:
                        continue
        return None

    # Join all lines in the JSON block into a single string
    json_string = "\n".join(json_lines).strip()
    
    # Try to parse the collected JSON lines
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        # Attempt to remove invalid control characters and re-parse
        json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
        try:
            return json.loads(json_string_clean)
        except json.JSONDecodeError:
            return None
