import pytest
from pathlib import Path
from tools.edit import tool_function

# Test fixtures
@pytest.fixture
def temp_file(tmp_path):
    file_path = tmp_path / "test.txt"
    content = "line 1\nline 2\nline 3\n"
    file_path.write_text(content)
    return str(file_path)

def test_str_replace_success(temp_file):
    # Test successful replacement
    result = tool_function(
        command="str_replace",
        path=temp_file,
        old_str="line 2\n",
        new_str="replaced line\n"
    )
    assert "Successfully replaced" in result
    assert Path(temp_file).read_text() == "line 1\nreplaced line\nline 3\n"

def test_str_replace_not_found(temp_file):
    # Test when old_str is not found
    result = tool_function(
        command="str_replace",
        path=temp_file,
        old_str="nonexistent",
        new_str="something"
    )
    assert "Could not find" in result
    # Original file should be unchanged
    assert Path(temp_file).read_text() == "line 1\nline 2\nline 3\n"

def test_str_replace_multiple_occurrences(temp_file):
    # First create a file with multiple occurrences
    Path(temp_file).write_text("same\nsame\nsame\n")
    result = tool_function(
        command="str_replace",
        path=temp_file,
        old_str="same\n",
        new_str="different\n"
    )
    assert "multiple" in result
    # Original file should be unchanged
    assert Path(temp_file).read_text() == "same\nsame\nsame\n"

def test_str_replace_missing_params(temp_file):
    # Test missing parameters
    result = tool_function(
        command="str_replace",
        path=temp_file,
    )
    assert "Missing required" in result

def test_str_replace_invalid_path():
    # Test with non-existent file
    result = tool_function(
        command="str_replace",
        path="/nonexistent/path",
        old_str="old",
        new_str="new"
    )
    assert "does not exist" in result