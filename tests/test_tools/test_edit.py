import pytest
from pathlib import Path
from tools.edit import tool_function

def test_view_line_range(tmp_path):
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_content = "line1\nline2\nline3\nline4\nline5\n"
    test_file.write_text(test_content)

    # Test viewing specific line range
    result = tool_function("view", str(test_file), view_range=[2, 4])
    assert "line2" in result
    assert "line3" in result
    assert "line4" in result
    assert "line1" not in result
    assert "line5" not in result
    assert "     2\t" in result  # Correct line numbering

    # Test viewing from start to middle
    result = tool_function("view", str(test_file), view_range=[1, 3])
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "line4" not in result
    assert "     1\t" in result

    # Test viewing from middle to end with -1
    result = tool_function("view", str(test_file), view_range=[3, -1])
    assert "line1" not in result
    assert "line2" not in result
    assert "line3" in result
    assert "line4" in result
    assert "line5" in result
    assert "     3\t" in result

def test_view_range_validation(tmp_path):
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_content = "line1\nline2\nline3\n"
    test_file.write_text(test_content)

    # Test invalid start line
    result = tool_function("view", str(test_file), view_range=[0, 2])
    assert "Failed to read file range: Start line must be >= 1" in result

    # Test invalid range (end < start)
    result = tool_function("view", str(test_file), view_range=[2, 1])
    assert "Failed to read file range: End line must be >= start line or -1" in result

def test_view_range_with_directory(tmp_path):
    # Test that view_range is rejected for directories
    result = tool_function("view", str(tmp_path), view_range=[1, 10])
    assert "Error: view_range is not supported for directory listings" in result