from pathlib import Path
import subprocess

def tool_info():
    return {
        "name": "editor",
        "description": """Custom editing tool for viewing, creating, and editing files\n
* State is persistent across command calls and discussions with the user.\n
* If `path` is a file, `view` displays the entire file with line numbers. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep.\n
* The `create` command cannot be used if the specified `path` already exists as a file.\n
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`.\n
* The `edit` command overwrites the entire file with the provided `file_text`.\n
* The `replace_block` command replaces a specified range of lines (from `start_line` to `end_line`, inclusive) with `block_content`. If `block_content` is an empty string, the specified lines are deleted. Newlines in `block_content` will result in multiple lines; content is typically joined by newlines to form the final text.\n
* No partial/line-range edits or partial viewing are supported for the basic `edit` or `view` commands (use `replace_block` for precise edits).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["view", "create", "edit", "replace_block"],
                    "description": "The command to run: `view`, `create`, `edit`, or `replace_block`."
                },
                "path": {
                    "description": "Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`.",
                    "type": "string"
                },
                "file_text": {
                    "description": "Required parameter of `create` or `edit` (full file overwrite) command, containing the content for the entire file.",
                    "type": "string"
                },
                "start_line": {
                    "description": "For `replace_block` command: The first line (inclusive, 1-indexed) of the block to be replaced. Must be a positive integer.",
                    "type": "integer"
                },
                "end_line": {
                    "description": "For `replace_block` command: The last line (inclusive, 1-indexed) of the block to be replaced. Must be a positive integer and greater than or equal to `start_line`.",
                    "type": "integer"
                },
                "block_content": {
                    "description": "For `replace_block` command: The new textual content to replace the specified block. Newlines (e.g., '\\n') will create multiple lines in the output. An empty string means the block will be deleted.",
                    "type": "string"
                }
            },
            "required": ["command", "path"]
        }
    }

def maybe_truncate(content: str, max_length: int = 10000) -> str:
    """Truncate long content and add marker."""
    if len(content) > max_length:
        return content[:max_length] + "\n<response clipped>"
    return content

def validate_path(path: str, command: str) -> Path:
    """
    Validate the file path for each command:
      - 'view': path may be a file or directory; must exist.
      - 'create': path must not exist (for new file creation).
      - 'edit': path must exist (for overwriting).
      - 'replace_block': path must exist and be a file (for replacing content).
    """
    path_obj = Path(path)

    # Check if it's an absolute path
    if not path_obj.is_absolute():
        raise ValueError(
            f"The path {path} is not an absolute path (must start with '/')."
        )

    if command == "view":
        # Path must exist
        if not path_obj.exists():
            raise ValueError(f"The path {path} does not exist.")
    elif command == "create":
        # Path must not exist
        if path_obj.exists():
            raise ValueError(f"Cannot create new file; {path} already exists.")
    elif command == "edit" or command == "replace_block":
        # Path must exist and must be a file
        if not path_obj.exists():
            raise ValueError(f"The file {path} does not exist.")
        if path_obj.is_dir():
            raise ValueError(f"{path} is a directory and cannot be edited as a file.")
    else:
        raise ValueError(f"Unknown or unsupported command: {command}")

    return path_obj

def format_output(content: str, path: str, init_line: int = 1) -> str:
    """Format output with line numbers (for file content)."""
    content = maybe_truncate(content)
    content = content.expandtabs()
    numbered_lines = [
        f"{i + init_line:6}\t{line}"
        for i, line in enumerate(content.split("\n"))
    ]
    return f"Here's the result of running `cat -n` on {path}:\n" + "\n".join(numbered_lines) + "\n"

def read_file(path: Path) -> str:
    """Read and return the entire file contents."""
    try:
        return path.read_text()
    except Exception as e:
        raise ValueError(f"Failed to read file: {e}")

def write_file(path: Path, content: str):
    """Write (overwrite) entire file contents."""
    try:
        path.write_text(content)
    except Exception as e:
        raise ValueError(f"Failed to write file: {e}")

def view_path(path_obj: Path) -> str:
    """View the entire file contents or directory listing."""
    if path_obj.is_dir():
        # For directories: list non-hidden files up to 2 levels deep
        try:
            result = subprocess.run(
                ['find', str(path_obj), '-maxdepth', '2', '-not', '-path', '*/\\.*'],
                capture_output=True,
                text=True
            )
            if result.stderr:
                return f"Error listing directory: {result.stderr}"
            return (
                f"Here's the files and directories up to 2 levels deep in {path_obj}, excluding hidden items:\n"
                + result.stdout
            )
        except Exception as e:
            raise ValueError(f"Failed to list directory: {e}")

    # If it's a file, show the entire file with line numbers
    content = read_file(path_obj)
    return format_output(content, str(path_obj))

def tool_function(command: str, path: str, file_text: str = None, **kwargs) -> str:
    """
    Main tool function that handles:
      - 'view'  : View the entire file or directory listing
      - 'create': Create a new file with the given file_text
      - 'edit'  : Overwrite an existing file with file_text
      - 'replace_block': Replaces a specific block of lines (inclusive) with new content.
                         Requires kwargs: start_line (int), end_line (int), block_content (str).
    """
    try:
        path_obj = validate_path(path, command)

        if command == "view":
            return view_path(path_obj)

        elif command == "create":
            if file_text is None:
                raise ValueError("Missing required `file_text` for 'create' command.")
            write_file(path_obj, file_text)
            return f"File created successfully at: {path}"

        elif command == "edit":
            if file_text is None:
                raise ValueError("Missing required `file_text` for 'edit' command.")
            write_file(path_obj, file_text)
            return f"File at {path} has been overwritten with new content."

        elif command == "replace_block":
            start_line = kwargs.get("start_line")
            end_line = kwargs.get("end_line")
            block_content = kwargs.get("block_content")

            if not (isinstance(start_line, int) and isinstance(end_line, int) and isinstance(block_content, str)):
                raise ValueError("Missing or invalid type for required arguments for 'replace_block': start_line (int), end_line (int), block_content (str).")

            if start_line <= 0 or end_line <= 0:
                raise ValueError("start_line and end_line must be positive integers for 'replace_block'.")
            if start_line > end_line:
                raise ValueError(f"start_line ({start_line}) cannot be greater than end_line ({end_line}) for 'replace_block'.")

            original_content_str = read_file(path_obj)
            original_lines = original_content_str.splitlines()
            total_lines = len(original_lines)

            new_content_str = ""

            if total_lines == 0: # Handling for empty file
                if start_line == 1 and end_line == 1:
                    new_content_str = block_content
                else:
                    raise ValueError(f"For an empty file, start_line and end_line must both be 1 to replace its content. Got start_line={start_line}, end_line={end_line}.")
            else: # Handling for non-empty file
                if not (1 <= start_line <= total_lines):
                    raise ValueError(f"start_line ({start_line}) is out of bounds for file with {total_lines} lines.")
                if not (start_line <= end_line <= total_lines):
                     raise ValueError(f"end_line ({end_line}) is out of bounds for file with {total_lines} lines or less than start_line ({start_line}).")

                new_content_list = []
                new_content_list.extend(original_lines[0:start_line-1]) # Lines before the block

                if block_content: # Add new block content if it's not empty
                    new_content_list.extend(block_content.splitlines())

                new_content_list.extend(original_lines[end_line:]) # Lines after the block

                new_content_str = "\n".join(new_content_list)

            # Ensure a final newline if the content is not empty and doesn't already have one
            if new_content_str and not new_content_str.endswith('\n'):
                new_content_str += '\n'

            # If new_content_str is empty (e.g., all lines deleted and block_content was empty),
            # write_file will correctly create an empty file.

            write_file(path_obj, new_content_str)
            return f"File {path} updated by replacing lines {start_line}-{end_line}."
        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    pass
