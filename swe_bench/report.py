import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess


def load_predictions(paths):
    prediction_paths = []
    for path in paths:
        path = Path(path)
        if path.is_file():
            prediction_paths.append(path)
        elif path.is_dir():
            prediction_paths += list(path.glob("*.json"))
        else:
            assert False, path

    predictions = dict()
    for fname in prediction_paths:
        try:
            pred = json.loads(fname.read_text())
        except json.decoder.JSONDecodeError as err:
            raise err

        if "instance_id" not in pred:
            print("Skipping json without instance_id", fname)
            continue

        inst = pred["instance_id"]
        pred["json_fname"] = str(fname)
        predictions[inst] = pred

    return predictions

def remove_patches_to_tests(model_patch):
    """
    Remove any changes to the tests directory from the provided patch.
    This is to ensure that the model_patch does not disturb the repo's
    tests when doing acceptance testing with the `test_patch`.
    """
    lines = model_patch.splitlines(keepends=True)
    filtered_lines = []
    is_tests = False

    for line in lines:
        if line.startswith("diff --git a/"):
            pieces = line.split()
            to = pieces[-1]
            if to.startswith("b/") and (
                    "/test/" in to
                    or "/tests/" in to
                    or "/testing/" in to
                    or "/test_" in to
                    or "/tox.ini" in to
            ):
                is_tests = True
            else:
                is_tests = False

        if not is_tests:
            filtered_lines.append(line)

    return "".join(filtered_lines)

def preds_to_jsonl(dname, predictions):
    dname = Path(dname)

    predictions_jsonl = str(dname / "all_preds.jsonl")
    model_name_or_path = list(predictions.values())[0]["model_name_or_path"]
    with open(predictions_jsonl, "w", encoding='utf-8') as fh:
        for inst, pred in predictions.items():
            assert model_name_or_path == pred["model_name_or_path"]
            minimal_pred = dict(
                model_name_or_path=model_name_or_path,
                model_patch=remove_patches_to_tests(pred["model_patch"]),
                instance_id=pred["instance_id"],
            )
            fh.write(json.dumps(minimal_pred) + "\n")
    return predictions_jsonl

def run_evals(predictions_jsonl, run_id, dataset_name, root_dir, output_dir, num_eval_procs=5):
    os.chdir(output_dir)  # switch dir so that things will be saved in the specified output_dir
    run_evals_cmd = f"""
python {os.path.join(root_dir, './swe_bench/SWE-bench/swebench/harness/run_evaluation.py')}
    --dataset_name {dataset_name}
    --predictions_path {predictions_jsonl}
    --max_workers {num_eval_procs}
    --run_id {run_id}
"""
    run_evals_cmd = " ".join([line.strip() for line in run_evals_cmd.split() if line.strip()])
    subprocess.run(run_evals_cmd.split(), check=True)
    os.chdir(root_dir)  # switch back to the original directory

def make_report(
        dnames,
        run_ids=None,
        dataset_name="princeton-nlp/SWE-bench_Verified",
        output_dir='./swe_bench',
        dnames_workers=None,
        num_eval_procs=5,
    ):
    """
    Generate reports for multiple directories in parallel.

    Args:
        dnames (list): List of directory names containing predictions.
        run_ids (list): Identifiers for the runs.
        dataset_name (str): Name of the dataset.
    """
    root_dir = os.path.abspath(os.getcwd())  # current working directory should be /dgm
    output_dir = os.path.join(root_dir, output_dir)

    def process_single_dname(dname, run_id):
        dname = Path(os.path.join(root_dir, dname))
        predictions = load_predictions([dname])
        predictions_jsonl = preds_to_jsonl(dname, predictions)
        run_evals(predictions_jsonl, run_id, dataset_name, root_dir, output_dir, num_eval_procs=num_eval_procs)
        print(f"Report generated for {dname}")
    
    # Use ThreadPoolExecutor to parallelize over dnames
    if run_ids is None or len(run_ids) != len(dnames):
        run_ids = [f"{i:03}" for i in range(len(dnames))]
    if dnames_workers is None:
        dnames_workers = len(dnames)
    with ThreadPoolExecutor(max_workers=dnames_workers) as executor:
        executor.map(process_single_dname, dnames, run_ids)

    print("All reports generated.")

def main():
    parser = argparse.ArgumentParser(description="Run evaluations on predictions.")
    parser.add_argument('--dnames', type=str, nargs='+', help="List of directories of predictions to evaluate.")
    parser.add_argument('--run_ids', type=str, nargs='+', default=None, help="Run ID for this evaluation run.")
    parser.add_argument('--dataset_name', type=str, default="princeton-nlp/SWE-bench_Verified", help="Name of the dataset to evaluate on.")
    parser.add_argument('--dnames_workers', type=int, default=None, help="Number of parallel workers to use for processing dnames.")
    parser.add_argument('--num_eval_procs', type=int, default=5, help="Number of parallel processes to use for evaluation.")
    parser.add_argument('--output_dir', type=str, default='./swe_bench', help="Output directory for the reports.")
    args = parser.parse_args()

    make_report(
        args.dnames,
        run_ids=args.run_ids,
        dataset_name=args.dataset_name,
        dnames_workers=args.dnames_workers,
        num_eval_procs=args.num_eval_procs,
        output_dir=args.output_dir,
    )

if __name__ == "__main__":
    main()
