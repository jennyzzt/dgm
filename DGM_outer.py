import argparse
import datetime
import json
import math
import os
import random
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed, TimeoutError

from prompts.self_improvement_prompt import find_selfimprove_eval_logs
from self_improve_step import self_improve
from utils.common_utils import load_json_file
from utils.docker_utils import setup_logger
from utils.evo_utils import load_dgm_metadata, is_compiled_self_improve

def initialize_run(output_dir, prevrun_dir=None, polyglot=False):
    # Initialize archive
    start_gen_num = 0
    if not prevrun_dir:
        archive = ['initial']
    else:
        # Load previous run's archive
        metadata_path = os.path.join(prevrun_dir, "dgm_metadata.jsonl")
        metadata = load_dgm_metadata(metadata_path, last_only=True)
        archive = metadata['archive']
        start_gen_num = metadata['generation'] + 1

    # Copy cached initial version into experiment dir
    initial_folder_name = 'initial' if not polyglot else 'initial_polyglot'
    if not prevrun_dir and not os.path.exists(f"{output_dir}/{initial_folder_name}"):
        if os.path.exists(initial_folder_name):
            os.system(f"cp -r {initial_folder_name}/ {output_dir}/initial")
        else:
            raise RuntimeError("Error: Need to properly configure evaluation results for the initial version.")
    
    return archive, start_gen_num

def any_exceeding_context_length(output_dir, commit_id, instance_ids):
    """
    Check if any of the issues have exceeded the context length.
    """
    for instance_id in instance_ids:
        md_logs, _, _, _ = find_selfimprove_eval_logs(instance_id, output_dir, commit_id, filter=False)
        md_log = md_logs[0]
        error_str = "Error in get_response_withtools: Error code: 400 - {'message': 'Input is too long for requested model.'}"
        # Repeated error_str means no attempt to fix it
        if f'{error_str}\n{error_str}' in md_log:
            return True
    return False

def choose_selfimproves(output_dir, archive, selfimprove_size, fusion_probability, method='random', run_baseline=None, polyglot=False):
    """
    Choose self-improve attempts for the current generation.
    May include single parent entries or two-parent fusion entries.
    """
    selfimprove_entries = []
    candidates = {}
    for commit in archive:
        try:
            metadata_path = os.path.join(output_dir, commit, "metadata.json")
            metadata = load_json_file(metadata_path)
            candidates[commit] = {
                'accuracy_score': metadata['overall_performance']['accuracy_score'],
                'total_unresolved_ids': metadata['overall_performance']['total_unresolved_ids'],
                'total_emptypatch_ids': metadata['overall_performance']['total_emptypatch_ids'],
                'total_resolved_ids': metadata['overall_performance']['total_resolved_ids'],
                'children_count': 0,
            }
            # update children count, parent should already be in the archive
            if commit != 'initial':
                parent_commit = metadata['parent_commit']
                candidates[parent_commit]['children_count'] += 1
        except Exception as e:
            # probably because swe-eval failed, generated code did not compile, etc.
            print(f"{commit} not eligible for being a parent: {e}")
            continue

    candidate_commits_list = list(candidates.keys())
    if not candidate_commits_list:
        # No eligible parents, return empty list
        return []

    for _ in range(selfimprove_size):
        attempt_fusion = random.random() < fusion_probability
        
        if attempt_fusion and len(candidate_commits_list) >= 2:
            parent1, parent2 = random.sample(candidate_commits_list, 2)
            selfimprove_entries.append(((parent1, parent2), "fuse_parents"))
            continue # Move to next attempt
        else:
            # Single parent selection (or fallback if len(candidate_commits_list) < 2)
            if not candidate_commits_list:
                continue

            parent_commit = None
            if run_baseline == 'no_darwin':
                parent_commit = candidate_commits_list[-1] # Always take the last commit
            elif method == 'score_prop':
                scores = [candidates[c]['accuracy_score'] for c in candidate_commits_list]
                # Sigmoid scaling for scores
                scaled_scores = [1 / (1 + math.exp(-10*(score-0.5))) for score in scores]
                if sum(scaled_scores) == 0: # Avoid division by zero if all scaled scores are 0
                    parent_commit = random.choice(candidate_commits_list)
                else:
                    probabilities = [s / sum(scaled_scores) for s in scaled_scores]
                    parent_commit = random.choices(candidate_commits_list, probabilities, k=1)[0]
            elif method == 'score_child_prop':
                scores = [candidates[c]['accuracy_score'] for c in candidate_commits_list]
                scaled_scores = [1 / (1 + math.exp(-10*(score-0.5))) for score in scores]
                children_counts = [candidates[c]['children_count'] for c in candidate_commits_list]
                # Inverse of children count (add 1 to avoid division by zero and to give less weight to more children)
                child_weights = [1 / (1 + count) for count in children_counts]

                combined_weights = [s * cw for s, cw in zip(scaled_scores, child_weights)]
                if sum(combined_weights) == 0:
                    parent_commit = random.choice(candidate_commits_list)
                else:
                    probabilities = [w / sum(combined_weights) for w in combined_weights]
                    parent_commit = random.choices(candidate_commits_list, probabilities, k=1)[0]
            elif method == 'best':
                # Sort by accuracy_score descending and pick the top one.
                # This means if multiple single-parent entries are made, they might all use the same best parent.
                parent_commit = sorted(candidate_commits_list, key=lambda c: candidates[c]['accuracy_score'], reverse=True)[0]
            else: # 'random' or default
                parent_commit = random.choice(candidate_commits_list)

            if parent_commit is None: # Should ideally not happen if candidate_commits_list is not empty
                continue

            empty_ids = candidates[parent_commit]['total_emptypatch_ids']
            resolved_ids = candidates[parent_commit]['total_resolved_ids']
            unresolved_ids = candidates[parent_commit]['total_unresolved_ids']

            if polyglot:
                entry_ids = empty_ids + unresolved_ids
                if not entry_ids:
                    entry_ids = resolved_ids + empty_ids + unresolved_ids
            else:
                num_total_ids = len(empty_ids) + len(resolved_ids) + len(unresolved_ids)
                if len(empty_ids) >= 0.1 * num_total_ids and random.random() < 0.25:
                    entry = 'solve_empty_patches'
                    selfimprove_entries.append((parent_commit, entry))
                    continue
                if random.random() < 0.25:
                    entry = 'solve_stochasticity'
                    selfimprove_entries.append((parent_commit, entry))
                    continue
                if any_exceeding_context_length(output_dir, parent_commit, empty_ids + unresolved_ids) and \
                    random.random() < 0.25:
                    entry = 'solve_contextlength'
                    selfimprove_entries.append((parent_commit, entry))
                    continue
                if not unresolved_ids: # Renamed from unresolved_ids == 0 for clarity
                    # If no specific entry type chosen and no unresolved, what to do?
                    # Maybe pick from resolved_ids or skip this parent for this iteration?
                    # For now, if no unresolved, we might not add an entry, leading to fewer than selfimprove_size.
                    # This needs to be handled: either ensure an entry or adjust loop.
                    # Current original code has `continue` if unresolved_ids == 0, which means
                    # it might also produce fewer than selfimprove_size entries.
                    # Let's keep that behavior for now.
                    if not (empty_ids + resolved_ids + unresolved_ids): # if truly no tasks at all
                        continue # skip this parent
                    entry_ids = unresolved_ids if unresolved_ids else (empty_ids + resolved_ids)


            if not entry_ids: # If after all logic, entry_ids is still empty (e.g. polyglot case with no tasks)
                # This case should ideally be prevented by ensuring 'candidates' only includes those with tasks,
                # or by having a default task. For now, skip adding an entry.
                continue

            entry = random.choice(entry_ids)
            selfimprove_entries.append((parent_commit, entry))

    return selfimprove_entries

def filter_compiled(run_ids, output_dir, num_swe_issues=[], logger=None):
    """
    Filter out runs that did not compile or have all empty patches.
    """
    run_ids_compiled = []

    logger.info(f"num_swe_issues: {num_swe_issues}")
    for run_id in run_ids:
        metadata_path = os.path.join(output_dir, run_id, "metadata.json")
        metadata = load_json_file(metadata_path)
        logger.info(f"{run_id} metadata: {metadata}")
        if is_compiled_self_improve(metadata, num_swe_issues=num_swe_issues, logger=logger):
            run_ids_compiled.append(run_id)
    return run_ids_compiled

def get_original_score(output_dir):
    """
    Get the original score from the initial version.
    """
    metadata = load_json_file(os.path.join(output_dir, "initial", "metadata.json"))
    return metadata["overall_performance"]["accuracy_score"]

def update_archive(output_dir, archive, new_ids, method='keep_all', noise_leeway=0.1):
    """
    Update the archive with the new self-improve runs.
    """
    if method == 'keep_better':
        # keep only better ones
        original_score = get_original_score(output_dir) - noise_leeway
        for run_id in new_ids:
            metadata = load_json_file(os.path.join(output_dir, run_id, "metadata.json"))
            score = metadata["overall_performance"]["accuracy_score"]
            if score >= original_score:
                archive.append(run_id)
    else:
        # keep everything
        archive += new_ids

    return archive

def get_full_eval_threshold(output_dir, archive):
    """
    Get the threshold for full evaluation.
    """
    archive_scores = []
    num_full_eval = sum(len(load_json_file(f"./swe_bench/subsets/{size}.json"))
                       for size in ['small', 'medium', 'big'])

    # Get original score
    original_score = get_original_score(output_dir)
    archive_scores.append(original_score)

    # Get scores from the archive
    for run_id in archive:
        metadata = load_json_file(os.path.join(output_dir, run_id, "metadata.json"))
        total_submitted_instances = metadata["overall_performance"]["total_submitted_instances"]
        # Skip if node did not have full evaluation
        if total_submitted_instances < num_full_eval * 0.9:
            continue
        score = metadata["overall_performance"]["accuracy_score"]
        archive_scores.append(score)

    # Get threshold, second highest score
    threshold = sorted(archive_scores, reverse=True)[1] if len(archive_scores) > 1 else archive_scores[0]
    # Ensure threshold is at least 0.4
    threshold = max(threshold, 0.4)

    return threshold

def main():
    parser = argparse.ArgumentParser(description="Darwin Godel Machine!")
    parser.add_argument("--max_generation", type=int, default=80, help="Maximum number of evolution iterations.")
    parser.add_argument("--selfimprove_size", type=int, default=2, help="Number of self-improvements attempts per DGM generation.")
    parser.add_argument("--selfimprove_workers", type=int, default=2, help="Number of parallel workers for self-improvement attempts.")
    parser.add_argument(
        "--choose_selfimproves_method", type=str, default='score_child_prop',
        choices=['random', 'score_prop', 'score_child_prop' 'best'],
        help="Method to choose self-improve attempts.",
    )
    parser.add_argument("--continue_from", type=str, default=None, help="Directory to continue the run from.")
    parser.add_argument("--update_archive", type=str, default='keep_all', choices=['keep_better', 'keep_all'], help="Method to update the archive.")
    # self-improve arguments
    parser.add_argument("--num_swe_evals", type=int, default=1, help="Number of repeated SWE evaluations to run for each self-improve attempt.")
    parser.add_argument('--post_improve_diagnose', default=False, action='store_true', help='Diagnose the self-improvement after evaluation')
    parser.add_argument("--shallow_eval", default=False, action='store_true', help="Run single shallow evaluation for self-improvement on swe.")
    parser.add_argument("--polyglot", default=False, action='store_true', help="Run single shallow evaluation for self-improvement on swe.")
    parser.add_argument("--eval_noise", type=float, default=0.1, help="Noise leeway for evaluation.")
    parser.add_argument("--no_full_eval", default=False, action='store_true', help="Do not run full evaluation on swe if a node is the top N highest performing.")
    # baselines # Use a more descriptive name for the argument for clarity.
    parser.add_argument("--run_baseline", type=str, default=None, choices=['no_selfimprove', 'no_darwin'], help="Baseline to run.")
    parser.add_argument("--fusion_probability", type=float, default=0.25, help="Probability of attempting a two-parent fusion.")
    args = parser.parse_args()

    # Variables for this DGM run
    if not args.continue_from:
        run_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S_%f")
    else:
        run_id = os.path.basename(args.continue_from)
        
    output_dir = os.path.join("./output_dgm", run_id)
    os.makedirs(output_dir, exist_ok=True)

    # Initialize
    archive, start_gen_num = initialize_run(output_dir, prevrun_dir=args.continue_from, polyglot=args.polyglot)

    # SWE issues to consider
    if not args.polyglot:
        swe_issues_sm = load_json_file("./swe_bench/subsets/small.json")
        swe_issues_med = load_json_file("./swe_bench/subsets/medium.json")
    else:
        swe_issues_sm = load_json_file("./polyglot/subsets/small.json")
        swe_issues_med = load_json_file("./polyglot/subsets/medium.json")

    # Set up logger
    logger = setup_logger(os.path.join(output_dir, "dgm_outer.log"))
    logger.info(f"Starting DGM run {run_id} with arguments: {vars(args)}")
    logger.info(f"Archive: {archive}")
    test_more_threshold = 0.4
    # Run the DGM
    for gen_num in range(start_gen_num, args.max_generation):
        # Choose self-improve attempts
        selfimprove_entries = choose_selfimproves(
            output_dir, archive, args.selfimprove_size,
            args.fusion_probability, # Pass the new argument
            method=args.choose_selfimproves_method,
            run_baseline=args.run_baseline,
            polyglot=args.polyglot,
        )
        logger.info(f"Self-improve entries for generation {gen_num}: {selfimprove_entries}")

        # Run self-improvement processes
        selfimprove_ids = []
        with ThreadPoolExecutor(max_workers=args.selfimprove_workers) as executor:
            futures = [
                executor.submit(
                    self_improve,
                    parent_commit=parent_commit,
                    output_dir=output_dir,
                    force_rebuild=False,
                    num_evals=args.num_swe_evals,
                    post_improve_diagnose=args.post_improve_diagnose,
                    entry=entry,
                    test_task_list=swe_issues_sm,
                    test_more_threshold=None if args.shallow_eval else test_more_threshold,
                    test_task_list_more=None if args.shallow_eval else swe_issues_med,
                    polyglot=args.polyglot,
                    full_eval_threshold=None if args.no_full_eval else get_full_eval_threshold(output_dir, archive),
                    run_baseline=args.run_baseline,
                )
                for parent_commit, entry in selfimprove_entries
            ]

            for future in as_completed(futures):
                try:
                    # Added timeout to avoid hanging indefinitely (1.5 h here)
                    metadata = future.result(timeout=1.5*60*60)
                    selfimprove_ids.append(metadata['run_id'])
                except TimeoutError:
                    logger.error("Self-improvement attempt timed out.")
                    future.cancel()  # Optionally cancel the future if it's still running
                except Exception as e:
                    import traceback
                    logger.error(f"Self-improvement step failed: {e}")
                    logger.error(f"Traceback:\n{traceback.format_exc()}")

        # Update archive
        logger.info(f"Updating archive for generation {gen_num}")
        selfimprove_ids_compiled = filter_compiled(
            selfimprove_ids,
            output_dir,
            num_swe_issues=[len(swe_issues_sm)] if args.shallow_eval else [len(swe_issues_sm), len(swe_issues_med)], logger=logger
        )
        archive = update_archive(output_dir, archive, selfimprove_ids_compiled, method=args.update_archive, noise_leeway=args.eval_noise)

        # Save DGM state
        with open(os.path.join(output_dir, "dgm_metadata.jsonl"), "a") as f:
            f.write(json.dumps({
                "generation": gen_num,
                "selfimprove_entries": selfimprove_entries,
                "children": selfimprove_ids,
                "children_compiled": selfimprove_ids_compiled,
                "archive": archive,
            }, indent=2) + "\n")

if __name__ == "__main__":
    main()

