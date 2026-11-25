import json
import subprocess

from polyglot.prepare_polyglot_dataset import register_git


def test_editor_file_in_initial_workspace(tmp_path, monkeypatch):
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.org")

    benchmark = tmp_path / "polyglot-benchmark"
    exercise = benchmark / "java/exercises/practice/rest-api"
    files = {
        "solution": ["src/main/java/RestApi.java"],
        "editor": ["src/main/java/Iou.java"],
        "test": ["src/test/java/RestApiTest.java"],
        "example": [".meta/reference/RestApi.java"],
    }
    for category, paths in files.items():
        for path in paths:
            source = exercise / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(category)
    (exercise / ".meta/config.json").write_text(json.dumps({"files": files}))

    base, full = register_git(benchmark)["java__rest-api"]

    def tracked_files(commit):
        output = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", commit], cwd=exercise, text=True
        )
        return set(output.splitlines())

    assert tracked_files(base) == set(files["solution"] + files["editor"])
    assert tracked_files(full) == tracked_files(base) | {
        ".meta/config.json", *files["test"], *files["example"]
    }
