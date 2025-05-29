import argparse
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import re

from llm_withtools import CLAUDE_MODEL, OPENAI_MODEL, chat_with_agent
from utils.eval_utils import get_report_score, msg_history_to_report, score_tie_breaker
from utils.git_utils import diff_versus_commit, reset_to_commit, apply_patch

# Thread-local storage for logger instances
thread_local = threading.local()

def get_thread_logger():
    """
    Get the logger instance specific to the current thread.
    Returns None if no logger has been set for this thread.
    """
    return getattr(thread_local, 'logger', None)

def set_thread_logger(logger):
    """
    Set the logger instance for the current thread.
    """
    thread_local.logger = logger

def setup_logger(log_file='./chat_history.md', level=logging.INFO):
    """
    Set up a logger with both file and console handlers.
    """
    # Create logger with a unique name based on thread ID
    logger = logging.getLogger(f'AgenticSystem-{threading.get_ident()}')
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatters
    file_formatter = logging.Formatter('%(message)s')
    
    # Create and set up file handler
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    
    # Store logger in thread-local storage
    set_thread_logger(logger)
    
    return logger

def safe_log(message, level=logging.INFO):
    """
    Thread-safe logging function that ensures messages go to the correct logger.
    """
    logger = get_thread_logger()
    if logger:
        logger.log(level, message)
    else:
        print(f"Warning: No logger found for thread {threading.get_ident()}")

def is_patch_valid(patch_str):
    """
    Parse the patch to check if any non-test source files are modified.
    Returns (bool, str) tuple: (is_valid, reason)
    """
    if not patch_str or patch_str.isspace():
        return False, "Empty patch"

    # Parse the patch to find modified files
    modified_files = []
    diff_header_pattern = re.compile(r'^\+\+\+ b/(.+)$', re.MULTILINE)
    for match in diff_header_pattern.finditer(patch_str):
        filepath = match.group(1)
        if filepath != '/dev/null':  # Skip deleted files
            modified_files.append(filepath)

    if not modified_files:
        return False, "No files modified"

    # Check if any non-test files are modified
    test_patterns = (
        lambda f: f.startswith('tests/'),
        lambda f: f.startswith('test_'),
        lambda f: f.endswith('_test.py')
    )

    source_files = [
        f for f in modified_files
        if not any(pattern(f) for pattern in test_patterns)
    ]

    if not source_files:
        return False, "Only test files were modified"

    return True, "Valid patch with source file modifications"

class AgenticSystem:
    def __init__(
            self,
            problem_statement,
            git_tempdir,
            base_commit,
            chat_history_file='./chat_history.md',
            test_description=None,
            self_improve=False,
            instance_id=None,
            max_retries=3,
            num_candidates=3,
        ):
        self.problem_statement = problem_statement
        self.git_tempdir = git_tempdir
        self.base_commit = base_commit
        self.chat_history_file = chat_history_file
        self.test_description = test_description
        self.self_improve = self_improve
        self.instance_id = instance_id if not self_improve else 'dgm'
        self.code_model = CLAUDE_MODEL
        self.max_retries = max_retries
        self.num_candidates = num_candidates

        # Initialize logger and store it in thread-local storage
        self.logger = setup_logger(chat_history_file)
        
        # Clear the log file
        with open(chat_history_file, 'w') as f:
            f.write('')

    def get_current_edits(self):
        diff = str(diff_versus_commit(self.git_tempdir, self.base_commit))
        return diff

    def get_regression_tests(self):
        """
        Get the regression tests from the repository.
        """
        instruction = f"""I have uploaded a Python code repository in the directory {self.git_tempdir}.

<problem_description>
{self.problem_statement}
</problem_description>

<test_description>
{self.test_description}
</test_description>

Your task is to identify regression tests in the {self.git_tempdir} directory that should pass both before and after addressing the <problem_description>. I have already taken care of the required dependencies.
At the end, please provide a summary that includes where the regression tests are located, what they are testing, and how they can be executed.
"""

        new_msg_history = chat_with_agent(instruction, model=self.code_model, msg_history=[], logging=safe_log)
        regression_tests_summary = new_msg_history[-1]
        try:
            regression_tests_summary = regression_tests_summary['content'][-1]['text']
        except:
            pass
        return regression_tests_summary

    def run_regression_tests(self, regression_tests_summary):
        """
        Run the regression tests and get the test report.
        """
        code_diff = self.get_current_edits()
        instruction = f"""I have uploaded a Python code repository in the directory {self.git_tempdir}. There is an attempt to address the problem statement. Please review the changes and run the regression tests.

<problem_description>
{self.problem_statement}
</problem_description>

<attempted_solution>
{code_diff}
</attempted_solution>

<test_description>
{self.test_description}
</test_description>

<regression_tests_summary>
{regression_tests_summary}
</regression_tests_summary>

Your task is to run the regression tests in the {self.git_tempdir} directory to ensure that the changes made to the code address the <problem_description>.
"""
        new_msg_history = chat_with_agent(instruction, model=self.code_model, msg_history=[], logging=safe_log)
        test_report = msg_history_to_report(self.instance_id, new_msg_history, model=self.code_model)
        return test_report

    def forward(self):
        """
        The forward function for the AgenticSystem that generates and evaluates multiple candidate patches.
        This version maintains history of prior valid patches and test results, only using the tie-breaker
        when necessary.
        """
        regression_tests_summary = self.get_regression_tests()

        # Lists to store all valid patches and their information
        valid_patches = []
        valid_reports = []
        valid_scores = []
        best_score = 0
        best_patches_indices = []  # Indices of patches that share the best score

        retry_count = 0
        while retry_count < self.max_retries and len(valid_patches) < self.num_candidates:
            safe_log(f"\n=== Attempt {retry_count + 1} of {self.max_retries} ===")
            safe_log(f"Valid solutions so far: {len(valid_patches)} of {self.num_candidates} desired")
            safe_log(f"Current best test score: {best_score}")

            # Reset to base commit before each attempt
            if retry_count > 0:
                reset_to_commit(self.git_tempdir, self.base_commit)

            # Construct instruction with previous best solutions if available
            instruction = f"""I have uploaded a Python code repository in the directory {self.git_tempdir}. Help solve the following problem.

<problem_description>
{self.problem_statement}
</problem_description>

<test_description>
{self.test_description}
</test_description>"""

            # Add previous solutions context if available
            if valid_patches and retry_count > 0:
                previous_solutions = []
                for i, (patch, report, score) in enumerate(zip(valid_patches, valid_reports, valid_scores)):
                    previous_solutions.append(f"""
Previous Solution {i+1}:
<code_changes>
{patch}
</code_changes>
Test Score: {score}
Test Report: {report}
""")
                instruction += "\n\nPrevious solution attempts:\n" + "\n".join(previous_solutions)
                instruction += "\nPlease provide a new solution that addresses any limitations in the previous attempts or explores a different approach."
            elif retry_count > 0:
                instruction += """\nNOTE: Previous attempt(s) did not produce enough valid solutions.
Please provide a different approach to solve the problem. Your solution must include changes to the main source code files, not just test files."""

            instruction += f"\n\nYour task is to make changes to the files in the {self.git_tempdir} directory to address the <problem_description>. I have already taken care of the required dependencies."

            # Run the agent
            new_msg_history = chat_with_agent(instruction, model=self.code_model, msg_history=[], logging=safe_log)

            # Check the patch
            patch = self.get_current_edits()
            is_valid, reason = is_patch_valid(patch)

            if is_valid:
                safe_log(f"✓ Valid patch generated: {reason}")
                # Run regression tests for this candidate
                test_report = self.run_regression_tests(regression_tests_summary)
                test_score = get_report_score(test_report)
                safe_log(f"Test score: {test_score}")

                valid_patches.append(patch)
                valid_reports.append(test_report)
                valid_scores.append(test_score)

                # Update best score and indices
                if test_score > best_score:
                    best_score = test_score
                    best_patches_indices = [len(valid_patches) - 1]
                elif test_score == best_score:
                    best_patches_indices.append(len(valid_patches) - 1)

                if len(valid_patches) >= self.num_candidates:
                    break
            else:
                safe_log(f"✗ Invalid patch: {reason}")

            retry_count += 1

        if not valid_patches:
            safe_log("Failed to generate any valid patches.")
            return

        # Only use tie-breaker if we have multiple patches with the best score
        safe_log(f"\n=== Selecting Best Solution from {len(valid_patches)} Candidates ===")
        if len(best_patches_indices) > 1:
            safe_log(f"Multiple solutions ({len(best_patches_indices)}) tied for best score {best_score}. Using tie-breaker.")
            best_index = score_tie_breaker(
                self.problem_statement,
                [valid_patches[i] for i in best_patches_indices],
                [valid_reports[i] for i in best_patches_indices],
                logging=safe_log
            )
            best_index = best_patches_indices[best_index]
        else:
            best_index = best_patches_indices[0]

        # Reset to base and apply the best patch
        reset_to_commit(self.git_tempdir, self.base_commit)
        best_patch = valid_patches[best_index]
        safe_log(f"\n=== Applying Best Solution (Candidate {best_index + 1}) with score {valid_scores[best_index]} ===")
        apply_patch(self.git_tempdir, best_patch)

        # Final validation of the selected patch
        final_test_report = self.run_regression_tests(regression_tests_summary)
        final_score = get_report_score(final_test_report)
        safe_log(f"Final validation test score: {final_score}")

def main():
    parser = argparse.ArgumentParser(description='Process repository with an agentic system.')
    parser.add_argument('--problem_statement', required=True, help='The problem statement to process')
    parser.add_argument('--git_dir', required=True, help='Path to git repository directory')
    parser.add_argument('--base_commit', required=True, help='Base commit hash to compare against')
    parser.add_argument('--chat_history_file', required=True, help='Path to chat history file')
    parser.add_argument('--outdir', required=False, default="/dgm/", help='Output directory')
    parser.add_argument('--test_description', default=None, required=False, help='Description of how to test the repository')
    parser.add_argument('--self_improve', default=False, action='store_true', help='Whether to self-improve the repository or solving swe')
    parser.add_argument('--instance_id', default=None, help='Instance ID for SWE issue')
    parser.add_argument('--max_retries', type=int, default=3, help='Maximum number of patch generation attempts')
    parser.add_argument('--num_candidates', type=int, default=3, help='Number of candidate solutions to generate')
    args = parser.parse_args()

    # Process the repository
    agentic_system = AgenticSystem(
        problem_statement=args.problem_statement,
        git_tempdir=args.git_dir,
        base_commit=args.base_commit,
        chat_history_file=args.chat_history_file,
        test_description=args.test_description,
        self_improve=args.self_improve,
        instance_id=args.instance_id,
        max_retries=args.max_retries,
        num_candidates=args.num_candidates,
    )

    # Run the agentic system to try to solve the problem
    agentic_system.forward()

    # Get code diff and save to model_patch.diff
    model_patch = diff_versus_commit(args.git_dir, args.base_commit)
    model_patch_outfile = os.path.join(args.outdir, 'model_patch.diff') if args.outdir else 'model_patch.diff'
    with open(model_patch_outfile, 'w') as f:
        f.write(model_patch)

if __name__ == "__main__":
    main()