import pytest
from coding_agent import is_patch_valid

def test_empty_patch():
    # Test empty patch
    is_valid, reason = is_patch_valid("")
    assert not is_valid
    assert reason == "Empty patch"

    # Test whitespace-only patch
    is_valid, reason = is_patch_valid("   \n   ")
    assert not is_valid
    assert reason == "Empty patch"

def test_test_only_patch():
    patch = """
diff --git a/tests/test_edit_tool.py b/tests/test_edit_tool.py
index abc123..def456 100644
--- a/tests/test_edit_tool.py
+++ b/tests/test_edit_tool.py
@@ -10,6 +10,8 @@ def test_something():
     assert True
+    assert 1 == 1
"""
    is_valid, reason = is_patch_valid(patch)
    assert not is_valid
    assert reason == "Only test files were modified"

def test_source_file_patch():
    patch = """
diff --git a/tools/edit.py b/tools/edit.py
index abc123..def456 100644
--- a/tools/edit.py
+++ b/tools/edit.py
@@ -10,6 +10,8 @@ class Editor:
     def edit(self):
         pass
+        return True
"""
    is_valid, reason = is_patch_valid(patch)
    assert is_valid
    assert reason == "Valid patch with source file modifications"

def test_mixed_files_patch():
    patch = """
diff --git a/tools/edit.py b/tools/edit.py
index abc123..def456 100644
--- a/tools/edit.py
+++ b/tools/edit.py
@@ -10,6 +10,8 @@ class Editor:
     def edit(self):
         pass
+        return True

diff --git a/tests/test_edit.py b/tests/test_edit.py
index abc123..def456 100644
--- a/tests/test_edit.py
+++ b/tests/test_edit.py
@@ -10,6 +10,8 @@ def test_something():
     assert True
+    assert 1 == 1
"""
    is_valid, reason = is_patch_valid(patch)
    assert is_valid
    assert reason == "Valid patch with source file modifications"

def test_no_files_modified():
    patch = """
diff --git a/nonexistent.py b/nonexistent.py
deleted file mode 100644
index abc123..0000000
--- a/nonexistent.py
+++ /dev/null
"""
    is_valid, reason = is_patch_valid(patch)
    assert not is_valid
    assert reason == "No files modified"