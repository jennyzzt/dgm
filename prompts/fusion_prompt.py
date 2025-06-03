def get_fusion_prompt(
    base_commit_id: str,
    parent1_commit_id: str,
    parent1_patch_content: str,
    parent2_commit_id: str,
    parent2_patch_content: str,
    existing_problem_statement: str = None
) -> str:
    """
    Generates a prompt for the LLM to perform a fusion of two parent diffs.
    """

    prompt = f"""You are an expert AI programmer. Your task is to perform a 'fusion' of code changes from two parent versions (Parent1 and Parent2) which both evolved from a common `base_commit`. The goal is to create a new child version that intelligently combines the beneficial features and improvements from both parents, applied to the `base_commit`.

The codebase is currently in the state of `base_commit` ('{base_commit_id}').

Here are the changes from `base_commit` to Parent1 ('{parent1_commit_id}'):
```diff
{parent1_patch_content}
```

Here are the changes from `base_commit` to Parent2 ('{parent2_commit_id}'):
```diff
{parent2_patch_content}
```

Your instructions for fusion are as follows:
1.  **Analyze Both Diffs**: Carefully study both diffs to understand the specific changes, enhancements, and fixes each parent introduced relative to the `base_commit`.
2.  **Primary Objective - Merge**: Your main goal is to apply the changes from *both* Parent1 and Parent2 onto the `base_commit` state. Try to incorporate the intent of both sets of changes.
3.  **Conflict Resolution**:
    *   If Parent1 and Parent2 modify the exact same lines of code in conflicting ways (e.g., changing a line to two different things), **prioritize the changes from Parent1.**
    *   If Parent1 deletes lines that Parent2 modifies, **the deletion by Parent1 takes precedence.**
    *   If Parent2 deletes lines that Parent1 modifies, **the deletion by Parent2 takes precedence.**
    *   If both parents delete the same set of lines, this is not a conflict; the lines are simply deleted.
    *   If one parent modifies a section of code and the other parent deletes the entire section, **the deletion takes precedence.**
4.  **Redundancy**: If both parents introduce identical changes (e.g., adding the exact same lines of code at the same location, or making the exact same modification), include these changes only once in the final merged code.
5.  **Coherence and Correctness**: Ensure the resulting code is coherent, syntactically correct, and logically sound. The combined changes should work together harmoniously.
6.  **Focus on Provided Diffs**: Do not introduce entirely new features, refactorings, or code changes that are not suggested by the content of Parent1's diff or Parent2's diff. Your task is to combine the given changes, not to add your own unrelated improvements.
"""

    if existing_problem_statement:
        prompt += f"\n7.  **Original Problem Context**: For your awareness, the original problem statement this lineage was trying to solve was: \"{existing_problem_statement}\". While fusing, ensure the fused result is still relevant to this problem, but prioritize the fusion instructions above.\n"
    else:
        prompt += "\n"

    prompt += """
Please use the available file editing tools to apply the combined and resolved changes directly to the codebase. Remember, the codebase is currently in the state of `base_commit`. Your edits will be captured as a new patch file representing the fused child.
"""
    return prompt
