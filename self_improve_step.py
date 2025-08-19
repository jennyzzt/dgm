import argparse
import datetime
import json
import os
import docker

from llm import create_client, get_response_from_llm, extract_json_between_markers
from prompts.self_improvement_prompt import get_diagnose_prompt_polyglot, get_diagnose_prompt_swe, get_problem_description_prompt
from prompts.diagnose_improvement_prompt import get_diagnose_improvement_prompt
from prompts.testrepo_prompt import get_test_description
from swe_bench.harness import harness
from polyglot.harness import harness as polyglot_harness
from swe_bench.report import make_report
from utils.common_utils import load_json_file
from utils.evo_utils import get_model_patch_paths, get_all_performance, is_compiled_self_improve
from utils.docker_utils import (
    build_dgm_container,
    cleanup_container,
    copy_from_container,
    copy_to_container,
    log_container_output,
    remove_existing_container,
    setup_logger,
    safe_log,
)

dataset = None
diagnose_model = 'o1-2024-12-17'

def diagnose_problem(entry, commit, root_dir, out_dir, patch_files=[], max_attempts=3, polyglot=False):
    client = create_client(diagnose_model)
    if polyglot:
        diagnose_sys_message, diagnose_prompt = get_diagnose_prompt_polyglot(
            entry, commit, root_dir, out_dir, dataset,
            patch_files=patch_files,
        )
    else:
        diagnose_sys_message, diagnose_prompt = get_diagnose_prompt_swe(
            entry, commit, root_dir, out_dir, dataset,
            patch_files=patch_files,
        )
    try:
        response, msg_history = get_response_from_llm(
            msg=diagnose_prompt,
            client=client[0],
            model=client[1],
            system_message=diagnose_sys_message,
            print_debug=False,
            msg_history=None,
        )
        safe_log(f"Message history: {msg_history}")
        response_json = extract_json_between_markers(response)
        assert response_json, "empty response json"
        problem_statement = get_problem_description_prompt(response_json, polyglot)
    except Exception as e:
        # Exception most probably due to not having json in the response
        safe_log(f"Error while diagnosing the problem: {e}")
        if max_attempts > 0:
            return diagnose_problem(
                entry, commit, root_dir, out_dir,
                patch_files=patch_files,
                max_attempts=max_attempts-1,
                polyglot=polyglot,
            )
        else:
            return None
    return problem_statement

def diagnose_improvement(
        entry, parent_commit, root_dir, model_patch_file, out_dir, run_id,
        patch_files=[], max_attempts=3,
    ):
    """
    Diagnose the improvement of the model patch.

    Args:
        entry (str): The task entry to improve.
        parent_commit (str): The commit hash of the parent commit.
        root_dir (str): The root directory of the repository.
        model_patch_file (str): The path to the model patch file.
        out_dir (str): The output directory.
        run_id (str): The run id of the self-improvement attempt.
        patch_files (list): The list of patch files before self-improvement.
        max_attempts (int): The maximum number of attempts to diagnose the improvement.
    
    Returns:
        dict: The improvement diagnosis.
    """
    client = create_client(diagnose_model)
    diagnose_sys_message, diagnose_prompt = get_diagnose_improvement_prompt(
        entry, parent_commit, root_dir, model_patch_file, out_dir, run_id, dataset,
        patch_files=patch_files,
    )
    safe_log(f"Diagnosing the improvement: {diagnose_prompt}")
    try:
        response, msg_history = get_response_from_llm(
            msg=diagnose_prompt,
            client=client[0],
            model=client[1],
            system_message=diagnose_sys_message,
            print_debug=False,
            msg_history=None,
        )
        safe_log(f"Message history: {msg_history}")
        response_json = extract_json_between_markers(response)
        assert response_json, "empty response json"
        improvement_diagnosis = response_json
    except Exception as e:
        # Exception most probably due to not having json in the response
        safe_log(f"Error while diagnosing the improvement: {e}")
        if max_attempts > 0:
            return diagnose_improvement(
                entry, parent_commit, root_dir, model_patch_file, out_dir, run_id,
                patch_files=patch_files, max_attempts=max_attempts-1,
            )
        else:
            return None
    return improvement_diagnosis

def save_metadata(metadata, output_dir):
    metadata_file = os.path.join(output_dir, "metadata.json")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=4)

def run_harness_swe(entry, model_name_or_path, patch_files, num_evals, output_dir, metadata, run_id, test_more_threshold, test_task_list, test_task_list_more):
    safe_log('Start harness')
    test_task_list = [entry] if test_task_list is None else test_task_list
    dnames = harness(
        test_task_list=test_task_list,
        num_samples=-1,
        max_workers=min(5, len(test_task_list)),
        model_name_or_path=model_name_or_path,
        model_patch_paths=patch_files,
        num_evals=num_evals,
        num_evals_parallel=5,
        pred_dname=os.path.join(output_dir, "predictions"),
    )
    metadata['swe_dnames'] = [str(dn) for dn in dnames]
    safe_log('Start make_report')
    make_report(
        dnames,
        run_ids=[f"{run_id}_{i}" for i in range(len(dnames))],
        dataset_name="princeton-nlp/SWE-bench_Verified",
        output_dir=output_dir,
        dnames_workers=5,
    )
    safe_log('Start get_performance')
    performances, overall_performance = get_all_performance(model_name_or_path, results_dir=output_dir)
    metadata['overall_performance'] = overall_performance
    safe_log("End of evaluation")

    # Check if additional evaluation should be run
    if (overall_performance and \
        test_more_threshold is not None and test_task_list_more is not None and \
            overall_performance.get('total_resolved_instances', 0) >= len(test_task_list) * test_more_threshold):
        safe_log("Start additional evaluation cycle")
        dnames = harness(
            test_task_list=test_task_list_more,
            num_samples=-1,
            max_workers=min(5, len(test_task_list_more)),
            model_name_or_path=model_name_or_path,
            model_patch_paths=patch_files,
            num_evals=num_evals,
            num_evals_parallel=5,
            pred_dname=os.path.join(output_dir, "predictions"),
        )
        safe_log('Start make_report more')
        make_report(
            dnames,
            run_ids=[f"{run_id}_{i}" for i in range(len(dnames))],
            dataset_name="princeton-nlp/SWE-bench_Verified",
            output_dir=output_dir,
            dnames_workers=5,
        )
        safe_log('Start get_performance')
        performances, overall_performance = get_all_performance(model_name_or_path, results_dir=output_dir)
        metadata['overall_performance'] = overall_performance
        safe_log("End of evaluation more")

def run_harness_polyglot(entry, model_name_or_path, patch_files, num_evals, output_dir, metadata, run_id, test_more_threshold, test_task_list, test_task_list_more):
    safe_log('Start harness')
    test_task_list = [entry] if test_task_list is None else test_task_list
    safe_log(f'workers {min(10, len(test_task_list))}')
    dnames = polyglot_harness(
        test_task_list=test_task_list,
        num_samples=-1,
        max_workers=min(10, len(test_task_list)),
        model_name_or_path=model_name_or_path,
        model_patch_paths=patch_files,
        num_evals=num_evals,
        num_evals_parallel=min(5, num_evals),
        pred_dname=os.path.join(output_dir, "predictions"),
        output_dir=output_dir
    )
    metadata['swe_dnames'] = [str(dn) for dn in dnames]
    safe_log('Start get_performance')
    performances, overall_performance = get_all_performance(model_name_or_path, results_dir=output_dir)
    metadata['overall_performance'] = overall_performance
    safe_log("End of evaluation")

    # Check if additional evaluation should be run
    if (overall_performance and \
        test_more_threshold is not None and test_task_list_more is not None and \
            overall_performance.get('total_resolved_instances', 0) >= len(test_task_list) * test_more_threshold):
        safe_log("Start additional evaluation cycle")
        dnames = polyglot_harness(
            test_task_list=test_task_list_more,
            num_samples=-1,
            max_workers=50,
            model_name_or_path=model_name_or_path,
            model_patch_paths=patch_files,
            num_evals=num_evals,
            num_evals_parallel=min(5, num_evals),
            pred_dname=os.path.join(output_dir, "predictions"),
            output_dir=output_dir
        )
        # metadata['swe_dnames'] = [str(dn) for dn in dnames]
        safe_log('Start get_performance')
        performances, overall_performance = get_all_performance(model_name_or_path, results_dir=output_dir)
        metadata['overall_performance_deep'] = overall_performance
        safe_log("End of evaluation more")

def self_improve(
    parent_commit='initial',  # 'initial' if starting from original dgm, else the run_id
    output_dir='output_selfimprove/',
    force_rebuild=False,
    num_evals=1,
    post_improve_diagnose=True,
    entry=None,
    test_task_list=None,  # None means the entry above only
    # Additional evaluation parameters
    test_more_threshold=None,
    test_task_list_more=None,
    full_eval_threshold=None,
    # Run baseline
    run_baseline=None,
    polyglot=False
):  

    global dataset
    if polyglot:
        with open("polyglot/polyglot_benchmark_metadata.json") as f:
            dataset = json.loads(f.read())
    else:
        from datasets import load_dataset
        dataset = load_dataset("princeton-nlp/SWE-bench_Verified")
        dataset = dataset['test']

    # Variables for this self-improvement attempt
    metadata = {}
    root_dir = os.path.abspath('./')  # root_dir should be /dgm
    run_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out_dir_base = output_dir  # out_dir_base should be /dgm/output_selfimprove/ or /dgm/output_dgm/{dgm_run_id}/
    output_dir = os.path.join(root_dir, f"{output_dir}/{run_id}/")
    os.makedirs(output_dir, exist_ok=True)
    metadata['run_id'] = run_id

    is_fusion = isinstance(parent_commit, tuple)
    base_commit = 'initial' # Hardcoded for now as per requirements

    if is_fusion:
        if entry != "fuse_parents":
            # This case should ideally not happen if DGM_outer.py is correct
            safe_log("Warning: parent_commit is a tuple, but entry is not 'fuse_parents'. Proceeding as fusion.")
        parent1_commit, parent2_commit = parent_commit
        metadata['parent_commits'] = [parent1_commit, parent2_commit]
        metadata['base_commit'] = base_commit
        metadata['parent_commit'] = None # Nullify to avoid confusion
        primary_parent_commit_for_patches = base_commit # Patches for agent are from base_commit
        safe_log(f"Fusion mode: Parent1={parent1_commit}, Parent2={parent2_commit}, Base={base_commit}")
    else:
        metadata['parent_commit'] = parent_commit
        primary_parent_commit_for_patches = parent_commit # Patches from this parent
        safe_log(f"Single parent mode: Parent={parent_commit}")

    test_task_list_big = load_json_file("./swe_bench/subsets/big.json")

    # Set up logger
    logger = setup_logger(os.path.join(output_dir, "self_improve.log"))

    # Create and start the Docker container
    image_name = "dgm"
    container_name = f"dgm-container-{run_id}"
    client = docker.from_env()
    # Remove any existing container with the same name
    remove_existing_container(client, container_name)
    # Now create and start the container
    container = build_dgm_container(
        client, root_dir, image_name, container_name,
        force_rebuild=force_rebuild,
    )
    container.start()

    if polyglot:
        # remove the swe version of coding_agent.py
        exec_result = container.exec_run("rm /dgm/coding_agent.py", workdir='/')
        log_container_output(exec_result)
        # rename coding_agent_polyglot.py to coding_agent.py
        exec_result = container.exec_run("mv /dgm/coding_agent_polyglot.py /dgm/coding_agent.py", workdir='/')
        log_container_output(exec_result)
        # remove swe-specific files utils/eval_utils.py and utils/swe_log_parsers.py
        exec_result = container.exec_run("rm /dgm/utils/eval_utils.py", workdir='/')
        log_container_output(exec_result)
        exec_result = container.exec_run("rm /dgm/utils/swe_log_parsers.py", workdir='/')
        log_container_output(exec_result)
    else:
        # remove the polyglot version of coding_agent.py
        exec_result = container.exec_run("rm /dgm/coding_agent_polyglot.py", workdir='/')

    # Find all parent patches and apply them
    # If fusion, the agent works from base_commit, so no prior patches are applied to bring it to parent1 or parent2.
    # The agent will be *aware* of parent1 and parent2's patches.
    # If not fusion, patches are applied to bring it to parent_commit's state.
    if is_fusion:
        patch_files = [] # Container starts from base_commit state for fusion agent
        # However, we need to know the patches for Parent1 and Parent2 for the agent
        # get_model_patch_paths always traces back to 'initial', which is our current base_commit.
        patch_files_parent1 = get_model_patch_paths(root_dir, os.path.join(output_dir, '../'), parent1_commit)
        patch_files_parent2 = get_model_patch_paths(root_dir, os.path.join(output_dir, '../'), parent2_commit)
        metadata['patch_files_parent1'] = patch_files_parent1
        metadata['patch_files_parent2'] = patch_files_parent2
        safe_log(f"Patch files for Parent1 (from {base_commit}): {patch_files_parent1}")
        safe_log(f"Patch files for Parent2 (from {base_commit}): {patch_files_parent2}")
    else:
        patch_files = get_model_patch_paths(root_dir, os.path.join(output_dir, '../'), primary_parent_commit_for_patches)

    if run_baseline not in ['no_selfimprove']:
        for patch_file in patch_files: # These are only applied if not fusion.
            copy_to_container(container, patch_file, '/dgm/parent_patch.txt')
            exec_result = container.exec_run("/bin/sh -c 'patch -p1 < /dgm/parent_patch.txt'", workdir='/dgm')
            log_container_output(exec_result)
            exec_result = container.exec_run("rm /dgm/parent_patch.txt", workdir='/dgm')
            log_container_output(exec_result)

    # Commit this version of dgm, so that irrelevant changes are not included in the patch
    # This commit represents the state the agent will start working from.
    # For fusion, this is base_commit. For single parent, this is parent_commit.
    exec_result = container.exec_run("git add --all", workdir='/dgm/')
    log_container_output(exec_result)
    exec_result = container.exec_run("git -c user.name='user' -c user.email='you@example.com' commit -m 'a nonsense commit message'", workdir='/dgm/')
    log_container_output(exec_result)
    commit_output = exec_result.output.decode('utf-8')
    # Git commit output format: `[master (root-commit) <hash>] a nonsense commit message`
    commit_hash = commit_output.split()[1].strip("[]")  # Extract the hash part

    # Install requirements again in case of any changes
    exec_result = container.exec_run("python -m pip install -r /dgm/requirements.txt", workdir='/')
    log_container_output(exec_result)

    # Get tasks to improve
    if is_fusion and entry == "fuse_parents":
        problem_statement = (
            f"Fuse features from Parent1 ({parent1_commit}) and Parent2 ({parent2_commit}) "
            f"based on the common ancestor ({base_commit})."
        )
        metadata['problem_statement_type'] = "fusion_predefined"
        safe_log(f"Fusion task problem statement: {problem_statement}")
    elif entry:
        safe_log(f"Task to improve: {entry}")
        # For diagnose_problem, use the actual single parent commit if not fusion,
        # or parent1 if fusion (though problem_statement is predefined for fusion, this call might be skipped or adapted)
        diagnose_parent_ref = parent1_commit if is_fusion else parent_commit
        problem_statement = diagnose_problem(entry, diagnose_parent_ref, root_dir, out_dir_base, patch_files=patch_files, polyglot=polyglot)
        metadata['problem_statement_type'] = "diagnosed"
        safe_log(f"problem_statement: {problem_statement}")
    else:
        safe_log("No entry provided. Exiting.")
        cleanup_container(container)
        save_metadata(metadata, output_dir)
        return metadata

    metadata['entry'] = entry
    metadata['problem_statement'] = problem_statement
    # If problem statement is not found, exit
    if not problem_statement:
        safe_log("Failed to diagnose the problem statement. Exiting.")
        cleanup_container(container)
        save_metadata(metadata, output_dir)
        return metadata

    # Run self-improvement
    model_patch_file = os.path.join(output_dir, "model_patch.diff") # Define early for cleanup
    model_patch_generated = False

    if is_fusion and entry == "fuse_parents":
        safe_log(f"Fusion mode: Preparing to call coding_agent.py for fusion. Base commit in container: {commit_hash}")

        # 1. Create concatenated diff files for parent1 and parent2
        host_p1_diff_path = os.path.join(output_dir, "parent1_for_fusion.diff")
        p1_content = []
        for p_file in metadata.get('patch_files_parent1', []):
            try:
                with open(p_file, 'r') as f:
                    p1_content.append(f.read())
            except FileNotFoundError:
                safe_log(f"Warning: Patch file {p_file} for parent1 not found. Skipping.")
        with open(host_p1_diff_path, 'w') as f:
            f.write("\n".join(p1_content))

        host_p2_diff_path = os.path.join(output_dir, "parent2_for_fusion.diff")
        p2_content = []
        for p_file in metadata.get('patch_files_parent2', []):
            try:
                with open(p_file, 'r') as f:
                    p2_content.append(f.read())
            except FileNotFoundError:
                safe_log(f"Warning: Patch file {p_file} for parent2 not found. Skipping.")
        with open(host_p2_diff_path, 'w') as f:
            f.write("\n".join(p2_content))

        # 2. Define container paths and copy these diff files to the container
        container_p1_diff_path = "/tmp/parent1_for_fusion.diff"
        container_p2_diff_path = "/tmp/parent2_for_fusion.diff"
        copy_to_container(container, host_p1_diff_path, container_p1_diff_path)
        copy_to_container(container, host_p2_diff_path, container_p2_diff_path)

        # 3. Construct command for coding_agent.py
        chat_history_file_container = "/dgm/self_evo_fusion.md" # Specific for fusion
        env_vars = {
            "ANTHROPIC_API_KEY": os.getenv('ANTHROPIC_API_KEY'),
            "AWS_REGION": os.getenv('AWS_REGION'),
            "AWS_REGION_NAME": os.getenv('AWS_REGION_NAME'),
            "AWS_ACCESS_KEY_ID": os.getenv('AWS_ACCESS_KEY_ID'),
            "AWS_SECRET_ACCESS_KEY": os.getenv('AWS_SECRET_ACCESS_KEY'),
            "OPENAI_API_KEY": os.getenv('OPENAI_API_KEY'),
        }
        cmd = [
            "timeout", "3600",  # Increased timeout for potentially complex fusion task (1hr)
            "python", "/dgm/coding_agent.py",
            "--problem_statement", problem_statement, # Predefined fusion problem statement
            "--git_dir", "/dgm/",
            "--chat_history_file", chat_history_file_container,
            "--base_commit", commit_hash, # SHA of 'initial' state in container
            "--outdir", "/dgm/",
            # Fusion specific arguments
            "--is_fusion_task",
            "--parent1_commit_id", parent1_commit,
            "--parent2_commit_id", parent2_commit,
            "--parent1_patch_file", container_p1_diff_path,
            "--parent2_patch_file", container_p2_diff_path,
            # --test_description might not be directly relevant for fusion prompt, but good to pass
            "--test_description", get_test_description(swerepo=False),
            "--self_improve" # Keep self_improve flag if it influences agent behavior generally
        ]

        safe_log(f"Executing fusion command: {' '.join(cmd)}")
        exec_result = container.exec_run(cmd, environment=env_vars, workdir='/')
        log_container_output(exec_result)

        # Copy output files (model_patch.diff, chat history) back to host
        chat_history_file = os.path.join(output_dir, "self_evo_fusion.md")
        copy_from_container(container, chat_history_file_container, chat_history_file)
        copy_from_container(container, "/dgm/model_patch.diff", model_patch_file)
        model_patch_generated = True

    elif problem_statement: # Proceed only if we have a problem statement (and not fusion)
        safe_log("Running self-improvement (single parent mode)")
        chat_history_file_container = "/dgm/self_evo.md" # Standard chat history file
        test_description = get_test_description(swerepo=False)
        env_vars = {
            "ANTHROPIC_API_KEY": os.getenv('ANTHROPIC_API_KEY'),
            "AWS_REGION": os.getenv('AWS_REGION'),
            "AWS_REGION_NAME": os.getenv('AWS_REGION_NAME'),
            "AWS_ACCESS_KEY_ID": os.getenv('AWS_ACCESS_KEY_ID'),
            "AWS_SECRET_ACCESS_KEY": os.getenv('AWS_SECRET_ACCESS_KEY'),
            "OPENAI_API_KEY": os.getenv('OPENAI_API_KEY'),
        }
        # TODO: For fusion, coding_agent.py will need different/additional arguments
        # like parent1_commit, parent2_commit, base_commit, and paths to their respective patches/code.
        cmd = [
            "timeout", "1800",  # 30min timeout
            "python", "/dgm/coding_agent.py",
            "--problem_statement", problem_statement,
            "--git_dir", "/dgm/",
            "--chat_history_file", chat_history_file_container,
            "--base_commit", commit_hash, # This is hash of (base_commit + patch_files) state
            "--outdir", "/dgm/",
            "--test_description", test_description,
            "--self_improve",
        ]
        exec_result = container.exec_run(cmd, environment=env_vars, workdir='/')
        log_container_output(exec_result)

        # Copy output files back to host
        chat_history_file = os.path.join(output_dir, "self_evo.md")
        copy_from_container(container, chat_history_file_container, chat_history_file)
        copy_from_container(container, "/dgm/model_patch.diff", model_patch_file)
        model_patch_generated = True
    else:
        safe_log("Skipping self-improvement agent call due to missing problem statement or other reasons.")

    if model_patch_generated:
        try:
            # Check if patch file exists and is not empty
            if not os.path.exists(model_patch_file):
                raise Exception("Model patch file is empty or does not exist")
            with open(model_patch_file, 'r') as f:
                patch_content = f.read()
                if not patch_content.strip():
                    raise Exception("Model patch file is empty")
            patch_files.append(model_patch_file) # Add successfully generated patch to list for evaluation
        except Exception as e:
            safe_log(f"Failed to read or validate model patch file: {str(e)}")
            model_patch_generated = False # Mark as not generated if checks fail
            # Do not return yet, proceed to cleanup and save metadata

    # Patch files for evaluation harness:
    # For fusion, it's just the new model_patch.diff (applied to 'initial').
    # For non-fusion, it's the chain of parent patches + new model_patch.diff.
    eval_patch_files = []
    if is_fusion:
        if model_patch_generated and os.path.exists(model_patch_file) and os.path.getsize(model_patch_file) > 0:
            eval_patch_files = [model_patch_file]
            safe_log(f"Fusion successful: using {model_patch_file} for evaluation.")
        else:
            safe_log("Fusion generated an empty or missing patch. Evaluation will run on base_commit state.")
            # eval_patch_files remains empty, harness runs on 'initial'
    else: # Non-fusion
        eval_patch_files = patch_files # These are patches leading up to current parent
        if model_patch_generated and os.path.exists(model_patch_file) and os.path.getsize(model_patch_file) > 0:
            eval_patch_files.append(model_patch_file)
            safe_log(f"Self-improve (single parent) successful: using {model_patch_file} on top of parent patches for evaluation.")
        else:
            safe_log("Self-improve (single parent) generated an empty or missing patch. Evaluation will run on parent state.")


    # Stop and remove the container
    cleanup_container(container)

    # Evaluate the performance of the self-improvement
    model_patch_exists = os.path.exists(model_patch_file) and model_patch_generated
    metadata['model_patch_exists'] = model_patch_exists
    model_patch_notempty = os.path.getsize(model_patch_file) > 0
    metadata['model_patch_notempty'] = model_patch_notempty
    model_name_or_path = run_id
    if model_patch_exists and model_patch_notempty:
        try:
            if not polyglot:
                run_harness_swe(entry, model_name_or_path, patch_files, num_evals, output_dir, metadata, run_id, test_more_threshold, test_task_list, test_task_list_more)
            else:
                run_harness_polyglot(entry, model_name_or_path, patch_files, num_evals, output_dir, metadata, run_id, test_more_threshold, test_task_list, test_task_list_more)
        except Exception as e:
            safe_log(f"Error while evaluating the self-improvement: {e}")

    # Post-self-improvement diagnosis
    if post_improve_diagnose:
        safe_log("Diagnosing the self-improvement")
        # is_compiled_self_improve uses metadata['overall_performance'] which is populated by run_harness_*
        # This check should occur *after* evaluation.
        # metadata['is_compiled'] = is_compiled_self_improve(metadata) # This seems premature here.

        # For diagnose_improvement, use parent1_commit if fusion, else original parent_commit
        diagnose_parent_ref_for_improvement = parent1_commit if is_fusion else parent_commit

        # Only diagnose if a patch was generated and exists, and if it compiled (checked after eval)
        if model_patch_exists:
            # We'll update metadata['is_compiled'] after evaluation, then this diagnosis can be more robust.
            # For now, we proceed assuming if patch exists, it might be diagnosable.
            # The actual diagnosis might need to happen after evaluation results are in metadata.
            # The `patch_files` argument to diagnose_improvement should be `eval_patch_files`
            improvement_diagnosis = diagnose_improvement(
                entry, diagnose_parent_ref_for_improvement, root_dir,
                model_patch_file, out_dir_base, run_id, # model_patch_file is the one generated by agent
                patch_files=eval_patch_files, # These are the patches applied for the eval run
            )
            metadata['improvement_diagnosis'] = improvement_diagnosis
            safe_log(f"Improvement diagnosis: {improvement_diagnosis}")
            else:
                safe_log("Skipping improvement diagnosis as no valid model patch was generated.")
                metadata['improvement_diagnosis'] = "No model patch generated."
        else:
            safe_log("The self-improvement fail to be complied")
            metadata['improvement_diagnosis'] = "Fail to complied. Ignore this."

    # Save metadata of this self-improvement attempt
    save_metadata(metadata, output_dir)
    return metadata

def main():
    parser = argparse.ArgumentParser(description="Self-improvement step for the repository.")
    parser.add_argument('--parent_commit', default="initial", type=str, help='Current commit to find the eval results, "initial" if starting from original dgm, else the run_id')
    parser.add_argument('--output_dir', default="./output_selfimprove", type=str, help='Directory to store the output')
    parser.add_argument('--force_rebuild', default=False, action='store_true', help='Force rebuild of the Docker image')
    parser.add_argument('--num_evals', default=1, type=int, help='Repeated number of swe evaluations after self-improvement')
    parser.add_argument('--no_post_improve_diagnose', default=False, action='store_true', help='Skip diagnosing the self-improvement after evaluation')
    parser.add_argument('--entry', default="django__django-10999", type=str, help='Task entry to improve')
    parser.add_argument('--test_task_list', default=None, type=str, help='List of tasks to evaluate the self-improvement')
    args = parser.parse_args()

    # Copy cached initial version into experiment dir
    os.system(f"cp -r initial/ {args.output_dir}")

    metadata = self_improve(
        parent_commit=args.parent_commit,
        output_dir=args.output_dir,
        force_rebuild=args.force_rebuild,
        num_evals=args.num_evals,
        post_improve_diagnose=not args.no_post_improve_diagnose,
        entry=args.entry,
        test_task_list=args.test_task_list,
    )

if __name__ == "__main__":
    main()
