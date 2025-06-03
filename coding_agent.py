
import argparse
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import os
import threading

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
            # Fusion task specific arguments
            is_fusion_task=False,
            parent1_patch_file=None,
            parent2_patch_file=None,
            parent1_commit_id=None,
            parent2_commit_id=None
        ):
        self.problem_statement = problem_statement
        self.git_tempdir = git_tempdir
        self.base_commit = base_commit # This is the SHA of the common ancestor for fusion
        self.chat_history_file = chat_history_file
        self.test_description = test_description
        self.self_improve = self_improve
        self.instance_id = instance_id if not self_improve else 'dgm'

        self.is_fusion_task = is_fusion_task
        self.parent1_patch_file = parent1_patch_file
        self.parent2_patch_file = parent2_patch_file
        self.parent1_commit_id = parent1_commit_id
        self.parent2_commit_id = parent2_commit_id

        self.code_model = CLAUDE_MODEL

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
        The forward function for the AgenticSystem.
        """
        if self.is_fusion_task:
            self.logger.info("Fusion task detected.")
            try:
                with open(self.parent1_patch_file, 'r') as f:
                    parent1_patch_content = f.read()
                with open(self.parent2_patch_file, 'r') as f:
                    parent2_patch_content = f.read()
            except FileNotFoundError as e:
                self.logger.error(f"Error: Parent patch file not found: {e}. This will result in an empty patch.")
                # Allow to proceed, will result in an empty diff as no chat_with_agent call
                return # Exit early, no instruction to run

            # Dynamically import here to avoid issues if this file is imported elsewhere
            # where prompts.fusion_prompt might not be immediately available or needed.
            from prompts.fusion_prompt import get_fusion_prompt

            instruction = get_fusion_prompt(
                base_commit_id=self.base_commit, # base_commit is the SHA of the common ancestor
                parent1_commit_id=self.parent1_commit_id,
                parent1_patch_content=parent1_patch_content,
                parent2_commit_id=self.parent2_commit_id,
                parent2_patch_content=parent2_patch_content,
                existing_problem_statement=self.problem_statement # Original problem statement for context
            )
            self.logger.info(f"Fusion instruction generated for base {self.base_commit}, P1 {self.parent1_commit_id}, P2 {self.parent2_commit_id}")
        else:
            self.logger.info("Standard task detected.")
            instruction = f"""I have uploaded a Python code repository in the directory {self.git_tempdir}. Help solve the following problem.

<problem_description>
{self.problem_statement}
</problem_description>

<test_description>
{self.test_description}
</test_description>

Your task is to make changes to the files in the {self.git_tempdir} directory to address the <problem_description>. I have already taken care of the required dependencies.
"""
        self.logger.info(f"Instruction for chat_with_agent (first 200 chars):\n{instruction[:200]}...")
        new_msg_history = chat_with_agent(instruction, model=self.code_model, msg_history=[], logging=safe_log)

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

    # Arguments for fusion task
    parser.add_argument("--is_fusion_task", default=False, action="store_true", help="Indicates if the task is a fusion of two parents.")
    parser.add_argument("--parent1_patch_file", type=str, default=None, help="Path to the diff file for Parent 1 (changes from base to P1). Required if is_fusion_task is True.")
    parser.add_argument("--parent2_patch_file", type=str, default=None, help="Path to the diff file for Parent 2 (changes from base to P2). Required if is_fusion_task is True.")
    parser.add_argument("--parent1_commit_id", type=str, default="Parent1", help="Commit ID for Parent 1 (for prompt context).")
    parser.add_argument("--parent2_commit_id", type=str, default="Parent2", help="Commit ID for Parent 2 (for prompt context).")

    args = parser.parse_args()

    if args.is_fusion_task and (not args.parent1_patch_file or not args.parent2_patch_file):
        parser.error("--parent1_patch_file and --parent2_patch_file are required when --is_fusion_task is True.")

    # Process the repository
    agentic_system = AgenticSystem(
        problem_statement=args.problem_statement,
        git_tempdir=args.git_dir,
        base_commit=args.base_commit,
        chat_history_file=args.chat_history_file,
        test_description=args.test_description,
        self_improve=args.self_improve,
        instance_id=args.instance_id,
        # Fusion arguments
        is_fusion_task=args.is_fusion_task,
        parent1_patch_file=args.parent1_patch_file,
        parent2_patch_file=args.parent2_patch_file,
        parent1_commit_id=args.parent1_commit_id,
        parent2_commit_id=args.parent2_commit_id
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
