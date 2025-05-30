<h1 align="center">
    Darwin Gödel Machine:<br/>Open-Ended Evolution of Self-Improving Agents
</h1>

<p align="center">
  <a href="https://github.com/jennyzzt/dgm/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge"></a>
  <a href="https://arxiv.org/abs/2505.22954"><img src="https://img.shields.io/badge/arXiv-2505.22954-b31b1b.svg?logo=arxiv&style=for-the-badge"></a>
  <a href="https://sakana.ai/dgm/"><img src="https://img.shields.io/badge/-Blog-%238D6748?style=for-the-badge&logo=Website&logoColor=white"></a>
  <a href="https://x.com/SakanaAILabs/status/1928272612431646943"><img src="https://img.shields.io/badge/twitter-%230077B5.svg?&style=for-the-badge&logo=twitter&logoColor=white&color=00acee"></a>
  <a href="https://drive.google.com/drive/folders/1Kcu9TbIa9Z50pJ7S6hH9omzzD1pxIYZC?usp=sharing"><img src="https://img.shields.io/badge/Experiment%20Logs-4285F4?style=for-the-badge&logo=googledrive&logoColor=white"></a>
</p>


Repository for **Darwin Gödel Machine (DGM)**, a novel self-improving system that iteratively modifies its own code (thereby also improving its ability to modify its own codebase) and empirically validates each change using coding benchmarks.

<p align="center">
  <img src="./misc/overview.gif" width="100%" height="auto" />
</p>
<!-- <p align="center">
<img src="./misc/conceptual.svg"/></a><br>
</p> -->


## Setup

### API Configuration
The Darwin Gödel Machine supports multiple LLM providers. Choose one of the following configurations:

#### Option 1: OpenRouter (Recommended - Single API Key)
```bash
# OpenRouter provides access to all models through one API key
export OPENROUTER_API_KEY='your_openrouter_api_key_here'
```

#### Option 2: Direct Provider APIs
```bash
# For direct access to provider APIs
export OPENAI_API_KEY='your_openai_api_key_here'
export ANTHROPIC_API_KEY='your_anthropic_api_key_here'

# Optional: For AWS Bedrock Claude models
export AWS_REGION='us-east-1'
export AWS_ACCESS_KEY_ID='your_aws_access_key_here'
export AWS_SECRET_ACCESS_KEY='your_aws_secret_key_here'

# Optional: For DeepSeek models
export DEEPSEEK_API_KEY='your_deepseek_api_key_here'
```

### Environment Configuration
Copy `.env.example` to `.env` and configure your preferred models:

```bash
cp .env.example .env
# Edit .env with your API keys and model preferences
```

```bash
# Verify that Docker is properly configured in your environment.
docker run hello-world
 
# If a permission error occurs, add the user to the Docker group
sudo usermod -aG docker $USER
newgrp docker
```

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: for running analysis
sudo apt-get install graphviz graphviz-dev
pip install -r requirements_dev.txt
```

```bash
# Clone SWE-bench
cd swe_bench
git clone https://github.com/princeton-nlp/SWE-bench.git
cd SWE-bench
git checkout dc4c087c2b9e4cefebf2e3d201d27e36
pip install -e .
cd ../../

# Prepare Polyglot
# Make sure git is properly configured in your environment with username and email
python polyglot/prepare_polyglot_dataset.py
```

## LLM Configuration

The Darwin Gödel Machine uses four different LLM roles that can be independently configured:

### Model Roles
1. **Coding Agent Model** (`CODING_AGENT_MODEL`): Primary model for code generation and modification
2. **Diagnosis Model** (`OPENAI_DIAGNOSIS_MODEL`): Model for problem analysis in self-improvement cycles
3. **Default OpenAI Model** (`DEFAULT_OPENAI_MODEL`): General-purpose model for tool use
4. **Evaluation Helper Model** (`EVAL_HELPER_MODEL`): Model for evaluation assistance and tie-breaking

### Available Models

#### OpenRouter Models (Recommended)
```bash
# Anthropic models via OpenRouter
anthropic/claude-3-5-sonnet-20241022    # Best for coding (recommended for CODING_AGENT_MODEL)
anthropic/claude-3-5-sonnet-20240620
anthropic/claude-3-haiku-20240307       # Fast and cost-effective
anthropic/claude-3-opus-20240229        # Most capable but expensive

# OpenAI models via OpenRouter
openai/o3-mini-2025-01-31              # Cost-effective (recommended for diagnosis/evaluation)
openai/o1-2024-12-17                   # Advanced reasoning
openai/gpt-4o-2024-08-06               # General purpose
openai/gpt-4o-mini-2024-07-18          # Cost-effective general purpose
```

#### Direct Provider Models
```bash
# Direct Anthropic API
claude-3-5-sonnet-20241022
claude-3-5-sonnet-20240620

# Direct OpenAI API
o3-mini-2025-01-31
o1-2024-12-17
gpt-4o-2024-08-06
gpt-4o-mini-2024-07-18

# AWS Bedrock Claude models
bedrock/us.anthropic.claude-3-5-sonnet-20241022-v2:0
bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0

# DeepSeek models
deepseek-chat
deepseek-coder
deepseek-reasoner

# Other OpenRouter models
llama3.1-405b
```

### Recommended Configurations

#### Cost-Optimized Setup
```bash
CODING_AGENT_MODEL="anthropic/claude-3-5-sonnet-20241022"  # Best coding performance
OPENAI_DIAGNOSIS_MODEL="openai/o3-mini-2025-01-31"        # Cost-effective reasoning
DEFAULT_OPENAI_MODEL="openai/o3-mini-2025-01-31"          # Cost-effective general use
EVAL_HELPER_MODEL="openai/o3-mini-2025-01-31"             # Cost-effective evaluation
```

#### Performance-Optimized Setup
```bash
CODING_AGENT_MODEL="anthropic/claude-3-5-sonnet-20241022"  # Best coding performance
OPENAI_DIAGNOSIS_MODEL="openai/o1-2024-12-17"             # Advanced reasoning
DEFAULT_OPENAI_MODEL="openai/gpt-4o-2024-08-06"           # High-quality general use
EVAL_HELPER_MODEL="openai/o1-2024-12-17"                  # Advanced evaluation
```

## Running the DGM
```bash
python DGM_outer.py
```
By default, outputs will be saved in the `output_dgm/` directory.

## File Structure
- `analysis/` scripts used for plotting and analysis
- `initial/` SWE-bench logs and performance of the initial agent
- `initial_polyglot/` Polyglot logs and performance of the initial agent
- `swe_bench/` code needed for SWE-bench evaluation
- `polyglot/` code needed for Polyglot evaluation
- `prompts/` prompts used for foundation models
- `tests/` tests for the DGM system
- `tools/` tools available to the foundation models
- `coding_agent.py` main implementation of the initial coding agent
- `DGM_outer.py` entry point for running the DGM algorithm

## Logs from Experiments
This [google drive folder](https://drive.google.com/drive/folders/1Kcu9TbIa9Z50pJ7S6hH9omzzD1pxIYZC?usp=sharing) contains all the foundation model output logs from the experiments shown in the paper.

## Safety Consideration
> [!WARNING]  
> This repository involves executing untrusted, model-generated code. We strongly advise users to be aware of the associated safety risks. While it is highly unlikely that such code will perform overtly malicious actions under our current settings and with the models we use, it may still behave destructively due to limitations in model capability or alignment. By using this repository, you acknowledge and accept these risks.

## Acknowledgement

The evaluation framework implementations are based on the [SWE-bench](https://github.com/swe-bench/SWE-bench) and [polyglot-benchmark](https://github.com/Aider-AI/polyglot-benchmark) repositories.

## Citing
If you find this project useful, please consider citing:
```bibtex
@article{zhang2025darwin,
  title={Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents},
  author={Zhang, Jenny and Hu, Shengran and Lu, Cong and Lange, Robert and Clune, Jeff},
  journal={arXiv preprint arXiv:2505.22954},
  year={2025}
}
```
