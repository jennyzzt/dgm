import pytest
from pathlib import Path
import tempfile
from tools.edit import tool_function

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)

@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file with content for testing."""
    file_path = temp_dir / "test.txt"
    content = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    file_path.write_text(content)
    return file_path

class TestEditorTool:
    def test_view_file(self, sample_file):
        """Test viewing entire file content."""
        result = tool_function("view", str(sample_file))
        assert "line 1" in result
        assert "line 5" in result
        assert "Here's the result of running `cat -n`" in result

    def test_create_file(self, temp_dir):
        """Test creating a new file."""
        new_file = temp_dir / "new.txt"
        content = "test content\nline 2"
        result = tool_function("create", str(new_file), file_text=content)
        assert "File created successfully" in result
        assert new_file.read_text() == content

    def test_create_existing_file(self, sample_file):
        """Test attempting to create an already existing file."""
        result = tool_function("create", str(sample_file), file_text="new content")
        assert "Error" in result
        assert "already exists" in result

    def test_edit_file(self, sample_file):
        """Test editing an existing file."""
        new_content = "edited content\nnew line"
        result = tool_function("edit", str(sample_file), file_text=new_content)
        assert "has been overwritten" in result
        assert sample_file.read_text() == new_content

    def test_edit_nonexistent_file(self, temp_dir):
        """Test attempting to edit a nonexistent file."""
        non_existent_file = temp_dir / "does_not_exist.txt"
        result = tool_function("edit", str(non_existent_file), file_text="new content")
        assert "Error" in result
        assert "does not exist" in result

    def test_view_directory(self, temp_dir):
        """Test viewing directory contents."""
        # Create some files in the directory
        (temp_dir / "file1.txt").touch()
        (temp_dir / "file2.txt").touch()
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").touch()

        result = tool_function("view", str(temp_dir))
        assert "files and directories" in result
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir" in result

    def test_invalid_path(self):
        """Test operations with invalid path."""
        result = tool_function("view", "/nonexistent/path")
        assert "Error" in result
        assert "does not exist" in result

    @pytest.mark.parametrize("command", [
        "unknown_command",
        "",
        None
    ])
    def test_invalid_commands(self, command, sample_file):
        """Test various invalid commands."""
        result = tool_function(command, str(sample_file))
        assert "Error" in result

class TestReplaceBlock:
    def test_replace_middle_block(self, sample_file):
        """Replace lines 2-3 with new content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=2,
            end_line=3,
            block_content="new line A\nnew line B"
        )
        assert f"File {sample_file} updated by replacing lines 2-3" in result
        expected_content = "line 1\nnew line A\nnew line B\nline 4\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_replace_at_start(self, sample_file):
        """Replace lines 1-2 with new content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=1,
            end_line=2,
            block_content="replacement for start"
        )
        assert f"File {sample_file} updated by replacing lines 1-2" in result
        expected_content = "replacement for start\nline 3\nline 4\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_replace_at_end(self, sample_file):
        """Replace lines 4-5 with new content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=4,
            end_line=5,
            block_content="replacement for end"
        )
        assert f"File {sample_file} updated by replacing lines 4-5" in result
        expected_content = "line 1\nline 2\nline 3\nreplacement for end\n"
        assert sample_file.read_text() == expected_content

    def test_replace_entire_file(self, sample_file):
        """Replace all lines (1-5) with new content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=1,
            end_line=5,
            block_content="all new content"
        )
        assert f"File {sample_file} updated by replacing lines 1-5" in result
        expected_content = "all new content\n"
        assert sample_file.read_text() == expected_content

    def test_replace_single_line(self, sample_file):
        """Replace line 3 with new content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=3,
            end_line=3,
            block_content="only line 3 replaced"
        )
        assert f"File {sample_file} updated by replacing lines 3-3" in result
        expected_content = "line 1\nline 2\nonly line 3 replaced\nline 4\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_delete_block_by_empty_content(self, sample_file):
        """Delete lines 2-4 by providing empty block_content."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=2,
            end_line=4,
            block_content=""
        )
        assert f"File {sample_file} updated by replacing lines 2-4" in result
        expected_content = "line 1\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_replace_with_fewer_lines(self, sample_file):
        """Replace lines 2-4 (3 lines) with 1 line."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=2,
            end_line=4,
            block_content="one line to replace three"
        )
        assert f"File {sample_file} updated by replacing lines 2-4" in result
        expected_content = "line 1\none line to replace three\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_replace_with_more_lines(self, sample_file):
        """Replace line 3 (1 line) with 3 lines."""
        result = tool_function(
            "replace_block",
            str(sample_file),
            start_line=3,
            end_line=3,
            block_content="line A\nline B\nline C"
        )
        assert f"File {sample_file} updated by replacing lines 3-3" in result
        expected_content = "line 1\nline 2\nline A\nline B\nline C\nline 4\nline 5\n"
        assert sample_file.read_text() == expected_content

    def test_replace_on_empty_file(self, temp_dir):
        """Test replace_block on an empty file."""
        empty_file = temp_dir / "empty.txt"
        empty_file.write_text("")

        result = tool_function(
            "replace_block",
            str(empty_file),
            start_line=1,
            end_line=1,
            block_content="content for empty file"
        )
        assert f"File {empty_file} updated by replacing lines 1-1" in result
        expected_content = "content for empty file\n"
        assert empty_file.read_text() == expected_content

    def test_invalid_line_numbers_non_positive(self, sample_file):
        """Test with non-positive line numbers."""
        result = tool_function("replace_block", str(sample_file), start_line=0, end_line=1, block_content="fail")
        assert "start_line and end_line must be positive integers" in result
        result = tool_function("replace_block", str(sample_file), start_line=1, end_line=0, block_content="fail")
        assert "start_line and end_line must be positive integers" in result

    def test_invalid_line_numbers_start_gt_end(self, sample_file):
        """Test with start_line > end_line."""
        result = tool_function("replace_block", str(sample_file), start_line=3, end_line=2, block_content="fail")
        assert "start_line (3) cannot be greater than end_line (2)" in result

    def test_invalid_line_numbers_out_of_bounds_non_empty_file(self, sample_file):
        """Test with line numbers out of file bounds for a non-empty file."""
        result = tool_function("replace_block", str(sample_file), start_line=6, end_line=6, block_content="fail")
        assert "start_line (6) is out of bounds for file with 5 lines" in result

        result = tool_function("replace_block", str(sample_file), start_line=1, end_line=6, block_content="fail")
        assert "end_line (6) is out of bounds for file with 5 lines" in result

    def test_invalid_line_numbers_for_empty_file(self, temp_dir):
        """Test invalid line numbers for an empty file."""
        empty_file = temp_dir / "empty.txt"
        empty_file.write_text("")
        result = tool_function("replace_block", str(empty_file), start_line=2, end_line=2, block_content="fail")
        assert "For an empty file, start_line and end_line must both be 1" in result

    def test_missing_parameters_for_replace_block(self, sample_file):
        """Test with missing required parameters for replace_block."""
        result = tool_function("replace_block", str(sample_file), start_line=1, end_line=1) # Missing block_content
        assert "Missing or invalid type for required arguments" in result
        result = tool_function("replace_block", str(sample_file), end_line=1, block_content="fail") # Missing start_line
        assert "Missing or invalid type for required arguments" in result
        result = tool_function("replace_block", str(sample_file), start_line=1, block_content="fail") # Missing end_line
        assert "Missing or invalid type for required arguments" in result

    def test_replace_block_nonexistent_file(self, temp_dir):
        """Test replace_block on a nonexistent file."""
        non_existent_file = temp_dir / "does_not_exist.txt"
        result = tool_function(
            "replace_block",
            str(non_existent_file),
            start_line=1,
            end_line=1,
            block_content="content"
        )
        assert "Error" in result
        assert "does not exist" in result
