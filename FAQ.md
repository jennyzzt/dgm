# Darwin Gödel Machine - Frequently Asked Questions

## LLM Configuration and Model Selection

### Q: Which LLM provider should I use?

**A:** We recommend **OpenRouter** for simplicity and cost-effectiveness:

- **Single API key** for all models
- **Competitive pricing** across providers
- **Easy model switching** without changing API configurations
- **Access to latest models** from multiple providers

### Q: What models should I use for each role?

**A:** The DGM uses four different LLM roles:

#### Recommended Configuration (Cost-Optimized)
```bash
CODING_AGENT_MODEL="anthropic/claude-3-5-sonnet-20241022"  # Best coding performance
OPENAI_DIAGNOSIS_MODEL="openai/o3-mini-2025-01-31"        # Cost-effective reasoning
DEFAULT_OPENAI_MODEL="openai/o3-mini-2025-01-31"          # Cost-effective general use
EVAL_HELPER_MODEL="openai/o3-mini-2025-01-31"             # Cost-effective evaluation
```

#### Performance-Optimized Configuration
```bash
CODING_AGENT_MODEL="anthropic/claude-sonnet-4"            # Latest, most advanced
OPENAI_DIAGNOSIS_MODEL="openai/o1-2024-12-17"             # Advanced reasoning
DEFAULT_OPENAI_MODEL="openai/gpt-4o-2024-08-06"           # High-quality general use
EVAL_HELPER_MODEL="openai/o1-2024-12-17"                  # Advanced evaluation
```

### Q: What's the difference between the four model roles?

**A:** Each role serves a specific purpose:

1. **Coding Agent Model**: Primary model for generating and modifying code
   - **Recommendation**: Claude Sonnet 4 (latest, most advanced) or Claude 3.5 Sonnet (proven performance)
   - **Usage**: Core self-improvement code generation

2. **Diagnosis Model**: Analyzes problems and failures in self-improvement cycles
   - **Recommendation**: O3-mini (cost-effective) or O1 (advanced reasoning)
   - **Usage**: Understanding why improvements failed

3. **Default OpenAI Model**: General-purpose model for tool use and utilities
   - **Recommendation**: O3-mini (cost-effective) or GPT-4o (higher quality)
   - **Usage**: Tool interactions and general tasks

4. **Evaluation Helper Model**: Assists with evaluation and tie-breaking decisions
   - **Recommendation**: O3-mini (cost-effective) or O1 (advanced analysis)
   - **Usage**: Comparing solutions and evaluation assistance

### Q: Can I use different providers for different roles?

**A:** Yes! You can mix and match providers:

```bash
# Example: OpenRouter for coding, direct OpenAI for reasoning
CODING_AGENT_MODEL="anthropic/claude-3-5-sonnet-20241022"  # OpenRouter
OPENAI_DIAGNOSIS_MODEL="o1-2024-12-17"                    # Direct OpenAI
DEFAULT_OPENAI_MODEL="openai/o3-mini-2025-01-31"          # OpenRouter
EVAL_HELPER_MODEL="o1-2024-12-17"                         # Direct OpenAI
```

### Q: What are the cost implications of different model choices?

**A:** Model costs vary significantly:

#### Cost Tiers (Approximate)
- **Most Expensive**: O1 models, Claude Opus
- **Moderate**: GPT-4o, Claude Sonnet
- **Cost-Effective**: O3-mini, GPT-4o-mini, Claude Haiku

#### Cost Optimization Tips
1. Use **O3-mini for diagnosis and evaluation** (high reasoning at low cost)
2. Use **Claude Sonnet only for coding** (where quality matters most)
3. Use **OpenRouter** for better pricing across providers
4. Monitor usage through provider dashboards

### Q: How do I switch between different model configurations?

**A:** Simply update your `.env` file:

```bash
# Edit .env file
nano .env

# Or export environment variables
export CODING_AGENT_MODEL="anthropic/claude-3-5-sonnet-20241022"
export OPENAI_DIAGNOSIS_MODEL="openai/o3-mini-2025-01-31"
```

Changes take effect on the next DGM run.

### Q: What if I want to use AWS Bedrock or other providers?

**A:** The system supports multiple providers:

#### AWS Bedrock
```bash
CODING_AGENT_MODEL="bedrock/us.anthropic.claude-3-5-sonnet-20241022-v2:0"
AWS_REGION="us-east-1"
AWS_ACCESS_KEY_ID="your_key"
AWS_SECRET_ACCESS_KEY="your_secret"
```

#### DeepSeek
```bash
CODING_AGENT_MODEL="deepseek-coder"
DEEPSEEK_API_KEY="your_deepseek_key"
```

#### Direct Provider APIs
```bash
CODING_AGENT_MODEL="claude-sonnet-4"             # Direct Anthropic (Latest)
OPENAI_DIAGNOSIS_MODEL="o1-2024-12-17"           # Direct OpenAI
ANTHROPIC_API_KEY="your_anthropic_key"
OPENAI_API_KEY="your_openai_key"
```

### Q: How do I know which models are available?

**A:** Check the `AVAILABLE_LLMS` list in [`llm.py`](llm.py:11-42) for all supported models:

- **OpenRouter models**: `anthropic/`, `openai/` prefixes
- **Direct provider models**: No prefix (e.g., `claude-3-5-sonnet-20241022`)
- **AWS Bedrock models**: `bedrock/` prefix
- **DeepSeek models**: `deepseek-` prefix
- **Other models**: Various specialized models

## Understanding DGM Results and Behavior

### Q: What does "compilation failed" mean in the DGM output?

**A:** "Compilation failed" is **normal and expected** in the DGM's evolutionary process. It means a self-improvement attempt didn't produce working code changes. This can happen for several reasons:

- **Empty patches**: The LLM didn't generate any meaningful code changes
- **Syntax errors**: The generated code had compilation issues
- **Logic errors**: The changes didn't pass basic validation tests
- **Context length issues**: The improvement attempt exceeded model token limits

**This is how evolution works** - most mutations fail, and only a small percentage provide advantages. The DGM learns from these failures to improve future attempts.

### Q: Is a 0% compilation success rate bad?

**A:** No, this is completely normal, especially for early DGM runs. The system is designed to:

- Learn from failed attempts
- Build knowledge about what doesn't work
- Gradually improve success rates over multiple generations
- Use failures as training data for better future attempts

Even with 0% compilation success, the DGM is gathering valuable information about the problem space.

### Q: How can I summarize what improvements the DGM attempted?

**A:** Use the [`summarize_improvements.py`](summarize_improvements.py:1) script:

```bash
# Analyze any DGM run
python summarize_improvements.py --path output_dgm/[RUN_ID]

# Save summary to file
python summarize_improvements.py --path output_dgm/[RUN_ID] --save
```

This provides:
- **Baseline performance** (initial agent SWE-bench accuracy)
- **Generation-by-generation breakdown** of attempts
- **Improvement strategy analysis** (what types of improvements were tried)
- **Compilation success tracking**
- **Performance comparison** when improvements succeed

### Q: What improvement strategies does the DGM typically attempt?

**A:** Common improvement strategies include:

- **`solve_stochasticity`**: Implementing multi-run evaluation workflows to handle agent randomness
- **`solve_empty_patches`**: Adding validation checks for empty/non-substantive patches
- **`solve_contextlength`**: Handling cases where input exceeds model context limits
- **Task-specific improvements**: Targeting specific SWE-bench tasks that failed
- **Architecture improvements**: Modifying the agent's core reasoning or tool usage

### Q: How do I know if the DGM is making progress?

**A:** Look for these indicators:

1. **Increasing compilation success rates** across generations
2. **Higher SWE-bench accuracy scores** in successful attempts
3. **More sophisticated improvement strategies** being attempted
4. **Fewer empty patches** and more substantive code changes
5. **Better problem diagnosis** in the improvement attempts

Use the analysis tools to track these metrics over time.

### Q: What should I do if all attempts fail compilation?

**A:** This is normal! Consider:

1. **Run more generations** - early failures often lead to later successes
2. **Increase worker count** - more parallel attempts increase chances of success
3. **Use different evaluation modes** - try both shallow and deep evaluation
4. **Check the improvement summaries** - failed attempts still provide learning value
5. **Review the specific failure logs** - they contain diagnostic information for future runs

### Q: How long should I expect a DGM run to take?

**A:** Timing depends on several factors:

- **Number of generations**: Each generation processes multiple improvement attempts
- **Worker count**: More workers = more parallel processing
- **Evaluation mode**: Shallow evaluation is faster than deep evaluation
- **Task complexity**: Some improvements require more extensive testing

Typical runs:
- **5 generations, 4 workers, shallow eval**: 30-60 minutes
- **10 generations, 8 workers, deep eval**: 2-4 hours

### Q: Can I interrupt and resume a DGM run?

**A:** Currently, DGM runs cannot be resumed if interrupted. Each run starts fresh. However:

- **Results are preserved** in the output directory
- **Failed attempts provide learning data** for subsequent runs
- **You can analyze partial results** using the analysis tools
- **Future versions may support checkpointing**

### Q: How do I interpret the SWE-bench accuracy scores?

**A:** SWE-bench accuracy represents the percentage of software engineering tasks the agent successfully resolves:

- **20% (baseline)**: Typical starting performance for coding agents
- **25-30%**: Good improvement showing meaningful progress
- **35%+**: Excellent performance, competitive with state-of-the-art systems
- **40%+**: Outstanding performance, approaching human-level on these tasks

The DGM aims to incrementally improve these scores through evolutionary self-improvement.

### Q: What files should I examine to understand what the DGM attempted?

**A:** Key files in each attempt directory:

- **`metadata.json`**: Contains performance metrics and attempt details
- **`model_patch.diff`**: The actual code changes attempted (if any)
- **`self_improve.log`**: Detailed log of the improvement process
- **`improvement_summary.txt`**: Generated summary of the entire run

Use the analysis tools to automatically parse and summarize this information.

## Getting Help

### Q: Where can I find more detailed documentation?

**A:** Check these resources:

- **[README.md](README.md)**: Main project documentation
- **[Memory Bank](memory-bank/)**: Detailed project context and architecture
- **Analysis tools**: [`analysis/`](analysis/) directory contains visualization scripts
- **This FAQ**: Updated based on common user questions

### Q: How do I report issues or ask questions?

**A:** For technical issues:

1. **Check this FAQ first** for common questions
2. **Review the logs** in your output directory
3. **Use the analysis tools** to understand what happened
4. **Create a GitHub issue** with relevant logs and context

For research questions or collaboration, refer to the project documentation for contact information.