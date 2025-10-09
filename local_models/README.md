Local GGUF Models Directory

This directory is used for local GGUF model discovery. The run script sets GGUF_MODEL_DIR to this path by default.

Structure
- Each model should have its own subfolder under this directory.
- Place exactly one or more .gguf files inside that subfolder. The code will pick the first .gguf it finds in the folder when using the `local/<folder>` provider or when resolving by bare model name via discovery.

Examples
- dgm/local_models/
  - llama-3.2-3b-instruct/
    - llama-3.2-3b-instruct.Q4_K_M.gguf
  - mistral-7b-instruct/
    - mistral-7b-instruct.Q4_K_M.gguf

Usage
- You can reference a model by its folder name using discovery, e.g. `--provider llama-cpp --model llama-3.2-3b-instruct` or `--provider local --model llama-3.2-3b-instruct`.
- Or point directly at a path, e.g. `--provider llama-cpp --model dgm/local_models/llama-3.2-3b-instruct/llama-3.2-3b-instruct.Q4_K_M.gguf`.

Environment
- Override the default by setting GGUF_MODEL_DIR to a different folder path.
- llama.cpp parameters can be tuned with environment vars:
  - LLAMA_CPP_N_CTX (default 8192)
  - LLAMA_CPP_N_GPU_LAYERS (default 0)
  - LLAMA_CPP_CHAT_FORMAT (default llama-3)
