import os

def get_tooluse_prompt():
    """
    Get the prompt for using the available tools.
    Prompt needed for LLMs without in-built tool calling.
    """
    # Get the available tools
    tool_folder = os.path.join(os.path.dirname(__file__), '../tools')
    tool_files = [
        os.path.join(tool_folder, file)
        for file in os.listdir(tool_folder)
        if file.endswith('.py') and file != '__init__.py'
    ]
    # Read the contents of the tool files
    tool_file_contents = [open(file, encoding='utf-8').read().strip() for file in tool_files]
    tools_available = [f"```python\n{tool_content}\n```" for tool_content in tool_file_contents]
    tools_available = '\n\n'.join(tools_available)
    # Create the prompt
    tooluse_prompt = """Here are the available tools:
{tools_available}

Use the available tools in this format:
```
<tool_use>
{{
    'tool_name': ...,
    'tool_input': ...
}}
</tool_use>
```
""".format(tools_available=tools_available)    
    return tooluse_prompt.strip()
