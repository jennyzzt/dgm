from pathlib import Path
import subprocess
from typing import Optional, List, Tuple, Union

def tool_info():
    return {
        "name": "editor",
        "description": """Custom editing tool for viewing, creating, and editing files\n
* State is persistent across command calls and discussions with the user.\n
* If `path` is a file, `view` displays the file with line numbers. With optional `view_range` [start, end], it displays only specified lines. Use -1 in `end` for all remaining lines.\n
* If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep.\n
* The `create` command cannot be used if the specified `path` already exists as a file.\n
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`.\n
* The `str_replace` command replaces a unique occurrence of old_str with new_str, failing if old_str is not found or appears multiple times.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["view", "create", "str_replace"],
                    "description": "The command to run: `view`, `create`, or `str_replace`."
                },
                "path": {
                    "description": "Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`.",
                    "type": "string"
                },
                "file_text": {
                    "description": "Required parameter of `create` command, containing the content for the entire file.",
                    "type": "string"
                },
                "view_range": {
                    "description": "Optional parameter for `view` command. Array of [start_line, end_line] (1-based). Use -1 for end_line to read until end of file.",
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2
                },
                "old_str": {
                    "description": "Required parameter of `str_replace` command, containing the exact text to find and replace.",
                    "type": "string"
                },
                "new_str": {
                    "description": "Required parameter of `str_replace` command, containing the new text to replace old_str with.",
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
      - 'str_replace': path must exist and be a file.
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
    elif command == "str_replace":
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

def read_file_range(path: Path, line_range: Optional[List[int]] = None) -> Tuple[str, int]:
    """
    Read and return file contents within specified line range.
    Returns tuple of (content, start_line).

    Args:
        path: Path object for the file
        line_range: Optional [start, end] line numbers (1-based). Use -1 for end to read until EOF.
    """
    try:
        if line_range is None:
            return read_file(path), 1

        start, end = line_range
        if start < 1:
            raise ValueError("Start line must be >= 1")
        if end != -1 and end < start:
            raise ValueError("End line must be >= start line or -1")

        with path.open() as f:
            # Skip lines before start
            for _ in range(start - 1):
                next(f, None)

            lines = []
            current_line = start
            while True:
                line = next(f, None)
                if line is None:  # EOF
                    break
                if end != -1 and current_line > end:
                    break
                lines.append(line.rstrip('\n'))
                current_line += 1

        return '\n'.join(lines), start

    except Exception as e:
        raise ValueError(f"Failed to read file range: {e}")

def write_file(path: Path, content: str):
    """Write (overwrite) entire file contents."""
    try:
        path.write_text(content)
    except Exception as e:
        raise ValueError(f"Failed to write file: {e}")

def str_replace_in_file(path: Path, old_str: str, new_str: str) -> str:
    """
    Replace an exact occurrence of old_str with new_str in the file.
    Only performs the replacement if old_str occurs exactly once.
    Returns a message indicating success or failure.
    """
    try:
        content = read_file(path)
        occurrences = content.count(old_str)

        if occurrences == 0:
            return f"Error: Could not find the exact text to replace in {path}"
        elif occurrences > 1:
            return f"Error: Found multiple ({occurrences}) occurrences of the text in {path}. Must be unique."
        else:
            new_content = content.replace(old_str, new_str)
            write_file(path, new_content)
            return f"Successfully replaced text in {path}"

    except Exception as e:
        return f"Error during string replacement: {e}"

def view_path(path_obj: Path, view_range: Optional[List[int]] = None) -> str:
    """
    View the file contents (optionally within a range) or directory listing.

    Args:
        path_obj: Path object for the file or directory
        view_range: Optional [start, end] line numbers for file viewing
    """
    if path_obj.is_dir():
        if view_range is not None:
            raise ValueError("view_range is not supported for directory listings")

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

    # If it's a file, show the file content (with optional line range)
    content, start_line = read_file_range(path_obj, view_range)
    return format_output(content, str(path_obj), start_line)

def tool_function(command: str, path: str, file_text: str = None, view_range: Optional[List[int]] = None,
                 old_str: str = None, new_str: str = None) -> str:
    """
    Main tool function that handles:
      - 'view'       : View file or directory listing, optionally within line range for files
      - 'create'     : Create a new file with the given file_text
      - 'str_replace': Replace exact occurrence of old_str with new_str in the file
    """
    try:
        path_obj = validate_path(path, command)

        if command == "view":
            return view_path(path_obj, view_range)

        elif command == "create":
            if file_text is None:
                raise ValueError("Missing required `file_text` for 'create' command.")
            write_file(path_obj, file_text)
            return f"File created successfully at: {path}"

        elif command == "str_replace":
            if old_str is None or new_str is None:
                raise ValueError("Missing required `old_str` and/or `new_str` for 'str_replace' command.")
            return str_replace_in_file(path_obj, old_str, new_str)

        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    # Example usage
    result = tool_function("view", "./coding_agent.py", view_range=[1, 10])
    print(result)
