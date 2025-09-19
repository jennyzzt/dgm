import json
import os
from pathlib import Path
import glob
import subprocess
from concurrent.futures import ThreadPoolExecutor
import git

from utils.git_utils import diff_versus_commit

import re

def modify_cmake_file(cmake_file_path, new_exercise_value):
    # Step 1: Read the CMake file
    with open(cmake_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Step 2: Find and modify the target line
    for i, line in enumerate(lines):
        if 'get_filename_component(exercise ${CMAKE_CURRENT_SOURCE_DIR} NAME)' in line:
            # Capture leading whitespace to preserve indentation
            leading_whitespace = re.match(r'\s*', line).group()
            # Replace the line with a set command using the new value
            lines[i] = leading_whitespace + f'set(exercise "{new_exercise_value}")\n'
            break

    # Step 3: Write the modified content back to the file
    with open(cmake_file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def extract_task_metadata(task_dir, all_commits):
    """Extract metadata for a single task directory"""
    
    # Get language and task name from path
    parts = task_dir.parts
    lang = parts[parts.index("polyglot-benchmark") + 1]
    task_name = parts[-1]
    instance_id = f"{lang}__{task_name}"
    
    metadata = {
        "instance_id": instance_id,
        "language": lang,
        "task_name": task_name,
        "files": {}
    }
    
    # Read config.json if it exists
    config_path = task_dir / ".meta" / "config.json"
    if config_path.exists():
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
            metadata.update({
                "authors": config.get("authors", []),
                "contributors": config.get("contributors", []),
                "blurb": config.get("blurb", ""),
                "source": config.get("source", ""),
                "source_url": config.get("source_url", "")
            })
            
            # Map file categories from config
            for category, files in config.get("files", {}).items():
                metadata["files"][category] = files

    # Read instructions if they exist
    docs_dir = task_dir / ".docs"
    if docs_dir.exists():
        problem_statement = ""
        for doc_file in docs_dir.glob("*.md"):
            with open(doc_file, encoding='utf-8') as f:
                problem_statement += f.read() + "\n\n"
        assert problem_statement, "Problem statement cannot be empty"
        metadata["problem_statement"] = problem_statement

    # Git related metadata
    solution_commit, all_files_commit = all_commits[instance_id]
    metadata["base_commit"] = solution_commit
    metadata["test_commit"] = all_files_commit

    # Solution
    test_files = config.get("files", {}).get("test", [])
    example_files = config.get("files", {}).get("example", [])

    # Concatenate test files content with filenames
    test_content = ""
    for test_file in test_files:
        test_file_path = task_dir / test_file
        if test_file_path.exists():
            test_content += f"### {test_file}\n"
            with open(test_file_path, encoding='utf-8') as f:
                test_content += f.read() + "\n\n"
    metadata["reference_tests"] = test_content

    # Get test patch (also full patch)
    metadata["test_patch"] = diff_versus_commit(task_dir, solution_commit)

    # Concatenate example files content with filenames
    example_content = ""
    for example_file in example_files:
        example_file_path = task_dir / example_file
        if example_file_path.exists():
            example_content += f"### {example_file}\n"
            with open(example_file_path, encoding='utf-8') as f:
                example_content += f.read() + "\n\n"
    metadata["reference_answers"] = example_content

    # Add absolute path of task directory
    metadata["repo"] = str(task_dir)

    return metadata

def generate_dataset_metadata(benchmark_dir, all_commits):
    """Generate metadata for all tasks in the benchmark directory"""
    
    benchmark_path = Path(benchmark_dir)
    all_metadata = []
    
    # Find all task directories (they contain .meta and .docs subdirs)
    # Process task directories in parallel with max 50 workers
    with ThreadPoolExecutor(max_workers=50) as executor:
        def process_task_dir(lang_dir):
            if lang_dir.is_dir() and (lang_dir / ".meta").exists() and (lang_dir / ".docs").exists():
                try:
                    task_metadata = extract_task_metadata(lang_dir, all_commits)
                    return task_metadata
                except Exception as e:
                    print(f"Error processing {lang_dir}: {e}")
                    return None

        # Map the processing function across all task directories
        task_dirs = (benchmark_path / "polyglot-benchmark").glob("*/exercises/practice/*")
        for metadata in executor.map(process_task_dir, task_dirs):
            if metadata:
                all_metadata.append(metadata)

    return all_metadata

def register_git(benchmark_path):
    """Initialize git repositories for each practice exercise folder if not already a git repo"""
    # Get list of practice directories that need git initialization
    practice_dirs = [
        d for d in benchmark_path.glob("*/exercises/practice/*/")
        if d.is_dir() and not (d / ".git").exists()
    ]

    if practice_dirs:
        print(f"Initializing git repositories for {len(practice_dirs)} practice directories...")
    else:
        print("All practice directories already initialized with git")
        commits_path = benchmark_path / "polyglot_benchmark_commits.json"
        if os.path.exists(commits_path):
            with open(commits_path, encoding='utf-8') as f:
                all_commits = json.load(f)
        else:
            raise FileNotFoundError(f"Commits file not found: {commits_path}")
        
        return all_commits
        
    # Process directories in parallel with max 50 workers
    with ThreadPoolExecutor(max_workers=50) as executor:
        def init_git_repo(practice_dir):
            try:
                parts = practice_dir.parts
                lang = parts[parts.index("polyglot-benchmark") + 1]
                task_name = parts[-1]
                instance_id = f"{lang}__{task_name}"

                # read meta data
                config_path = practice_dir / ".meta" / "config.json"
                if config_path.exists():
                    with open(config_path, encoding='utf-8') as f:
                        config = json.load(f)
                else:
                    raise FileNotFoundError(f"Config file not found: {config_path}")

                solution_files = set(config.get("files", {}).get("solution", []))
                if not solution_files:
                    raise ValueError(f"No solution files found in config for {practice_dir}")

                # init commit only with solution files
                subprocess.run(["git", "init"], cwd=practice_dir, check=True)
                for solution_file in solution_files:
                    subprocess.run(["git", "add", solution_file], cwd=practice_dir, check=True)
                # Add .docs folder if it exists
                adding_files = [".docs/"]

                # For different language, add necessary files
                if lang == 'java':
                    adding_files.extend(['gradle/', 'build.gradle', 'gradlew', 'gradlew.bat']) 
                elif lang == 'cpp':
                    modify_cmake_file(practice_dir / "CMakeLists.txt", task_name)
                    adding_files.extend(["test/", "CMakeLists.txt"])
                elif lang == 'javascript':
                    adding_files.extend([".eslintrc", '.npmrc', 'package.json'])

                for adding_file in adding_files:
                    if (practice_dir / adding_file).exists():
                        subprocess.run(["git", "add", adding_file], cwd=practice_dir, check=True)
                subprocess.run(["git", "status"], cwd=practice_dir, check=True)
                subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=practice_dir, check=True)
                # Get initial commit hash
                result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=practice_dir, check=True, capture_output=True, text=True)
                solution_commit = result.stdout.strip()

                # Then adding everything else
                subprocess.run(["git", "add", "."], cwd=practice_dir, check=True)
                subprocess.run(["git", "commit", "--amend", "-m", "all files"], cwd=practice_dir, check=True)
                
                all_files_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=practice_dir, check=True, capture_output=True, text=True).stdout.strip()

                return {instance_id: (solution_commit, all_files_commit)}

            except subprocess.CalledProcessError as e:
                print(f"Error initializing git in {practice_dir}: {e}")

        # Map the git init function across all practice directories with progress bar
        # Combine all returned dicts into one big dict
        all_commits = {}
        for result in executor.map(init_git_repo, practice_dirs):
            if result:  # Skip any None results from errors
                all_commits.update(result)
        # Save all_commits dict to JSON file
        commits_path = benchmark_path / "polyglot_benchmark_commits.json"
        with open(commits_path, "w", encoding='utf-8') as f:
            json.dump(all_commits, f, indent=2)
        print(f"Saved commit hashes to {commits_path}")
        
    return all_commits
        
def main():
    # Assuming script is run from the polyglot directory
    benchmark_dir = "polyglot"

    # Check if polyglot-benchmark exists, if not clone it
    benchmark_path = Path(benchmark_dir) / "polyglot-benchmark"
    if not benchmark_path.exists():
        print("Cloning polyglot-benchmark repository to", str(benchmark_path), "...")
        subprocess.run(
            ["git", "clone", "https://github.com/Aider-AI/polyglot-benchmark.git", str(benchmark_path)],
            check=True
        )
    else:
        print(f"Found polyglot-benchmark at {benchmark_path}")
    
    all_commits = register_git(benchmark_path)
    
    metadata = generate_dataset_metadata(benchmark_dir, all_commits)
    
    # Write metadata to JSON file
    output_path = "polyglot/polyglot_benchmark_metadata.json"
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Generated metadata for {len(metadata)} tasks")
    print(f"Metadata written to {output_path}")

if __name__ == "__main__":
    main()