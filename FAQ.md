# Darwin Gödel Machine - Frequently Asked Questions

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