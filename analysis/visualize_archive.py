import argparse
import os
import json
import math
import networkx as nx
import plotly.graph_objects as go

from utils.evo_utils import get_model_patch_paths, load_dgm_metadata


class EvalQuantity:
    SMALL = "small"
    MED = "med"
    BIG = "big"

def to_eval_quantity_enum(eval_quantity, halluc=False):
    # Convert a number to the corresponding EvalQuantity enum
    if halluc:
        if eval_quantity <= 1.5:
            return EvalQuantity.SMALL
        else:
            return EvalQuantity.BIG
    else:
        if eval_quantity <= 10:
            return EvalQuantity.SMALL
        elif eval_quantity <= 60:
            return EvalQuantity.MED
        else:
            return EvalQuantity.BIG

def get_evalquantity(dgm_dir, node_id, metadata_name="metadata.json", halluc=False):
    """
    Retrieve the eval_quantity from the metadata of a node.
    """
    metadata_path = os.path.join(dgm_dir, node_id, metadata_name)
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found for node {node_id} at {metadata_path}")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    overall_performance = metadata.get("overall_performance", {})
    eval_quantity = overall_performance.get("total_submitted_instances", 0) if overall_performance else 0
    return to_eval_quantity_enum(eval_quantity, halluc=halluc)

def get_parent_commit(dgm_dir, child_node_id, metadata_name="metadata.json"):
    """
    Retrieve the parent commit from the metadata of a child node.
    """
    metadata_path = os.path.join(dgm_dir, child_node_id, metadata_name)
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found for node {child_node_id} at {metadata_path}")
    with open(metadata_path, "r", encoding='utf-8') as f:
        metadata = json.load(f)
    return metadata.get("parent_commit")


def get_performance_score(dgm_dir, node_id, metadata_name="metadata.json"):
    """
    Retrieve the accuracy_score from the metadata of a node.
    """
    metadata_path = os.path.join(dgm_dir, node_id, metadata_name)
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found for node {node_id} at {metadata_path}")
    with open(metadata_path, "r", encoding='utf-8') as f:
        metadata = json.load(f)
    overall_performance = metadata.get("overall_performance", {})
    score = overall_performance.get("accuracy_score", 0.0) if overall_performance else 0.0
    return round(score, 2)


def get_hallucination_score(dgm_dir, node_id, metadata_name="metadata.json"):
    """
    Retrieve the 'solved_halluc_score' and, if it's 1, add the 'percent_toolutilized' from
    the metadata of a node. The final range of this score is [0, 2].
    """
    metadata_path = os.path.join(dgm_dir, node_id, metadata_name)
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found for node {node_id} at {metadata_path}")
    with open(metadata_path, "r", encoding='utf-8') as f:
        metadata = json.load(f)

    halluc_perf = metadata.get("hallucination_performance", {})
    solved_halluc_score = halluc_perf.get("solved_halluc_score", 0.0)
    final_score = solved_halluc_score
    if final_score == 1.0:
        # Only add percent_toolutilized if solved_halluc_score is 1
        percent_toolutilized = halluc_perf.get("percent_toolutilized", 0.0)
        final_score += percent_toolutilized  # can be up to 2.0

    return round(final_score, 2)


def build_graph(dgm_dir, archives, score_func, metadata_name="metadata.json"):
    """
    Generic helper to build a DiGraph with node attributes from the archives.
    score_func is a callable that returns a metric given (dgm_dir, node_id, metadata_name).
    Returns an (nx.DiGraph, pos) tuple, where pos is the Graphviz layout positions.
    """
    graph = nx.DiGraph()

    # Add the root node
    root_node = "initial"
    initial_metadata_path = os.path.join(dgm_dir, "initial", metadata_name)
    with open(initial_metadata_path, "r", encoding='utf-8') as f:
        initial_metadata = json.load(f)

    # Root node metric score
    if score_func == get_performance_score:
        root_node_evalquant = to_eval_quantity_enum(initial_metadata.get("overall_performance", 0).get("total_submitted_instances", 0))
        root_node_score = initial_metadata.get("overall_performance", {}).get("accuracy_score", 0.0)
    else:
        root_node_evalquant = to_eval_quantity_enum(initial_metadata.get("overall_performance", 0).get("total_submitted_instances", 0), halluc=True)
        halluc_perf = initial_metadata.get("hallucination_performance", {})
        solved_halluc_score = halluc_perf.get("solved_halluc_score", 0.0)
        root_node_score = solved_halluc_score
        if root_node_score == 1.0:
            tool_util = halluc_perf.get("percent_toolutilized", 0.0)
            root_node_score += tool_util

    index = 0
    graph.add_node(
        root_node,
        run_id=root_node,
        compiled=True,
        archived=True,
        score=round(root_node_score, 2),
        eval_quantity=root_node_evalquant,
        index=index,
    )

    # Build out from the archive data
    for archive in archives:
        children = archive.get("children", [])
        children_compiled = archive.get("children_compiled", [])
        children_archived = archive.get("archive", [])
        for child_node_id in children:
            parent_commit = get_parent_commit(dgm_dir, child_node_id, metadata_name=metadata_name)
            compiled = (child_node_id in children_compiled)
            archived = (child_node_id in children_archived)

            # If not compiled, force the score to 0
            if not compiled:
                metric_score = 0.0
            else:
                metric_score = score_func(dgm_dir, child_node_id, metadata_name=metadata_name)

            # Get the eval quantity
            eval_quantity = get_evalquantity(dgm_dir, child_node_id, metadata_name=metadata_name, halluc=(score_func == get_hallucination_score))

            index += 1
            graph.add_node(
                child_node_id,
                run_id=child_node_id,
                compiled=compiled,
                archived=archived,
                score=metric_score,
                eval_quantity=eval_quantity,
                index=index,
            )
            graph.add_edge(parent_commit, child_node_id)

    # Extract positions using Graphviz layout
    pos = nx.nx_agraph.graphviz_layout(graph, prog="dot")
    return graph, pos


def create_plotly_figure(graph, pos, html_path, colorbar_title="Score"):
    """
    Given a graph and node positions (pos),
    create and save a Plotly HTML figure that visualizes the graph.

    - Computes cmin/cmax by rounding to 0.1 intervals.
    - Finds the path from 'initial' to the highest-scoring node.
    - Draws that entire lineage thicker, but retains each edge’s color.
    """

    # 1) Identify the best node
    scores = {n: data['score'] for n, data in graph.nodes(data=True)}
    if not scores:
        raise ValueError("Graph has no nodes")
    best_node = max(scores, key=scores.get)

    # 2) Path from 'initial' -> best_node
    try:
        path = nx.shortest_path(graph, source='initial', target=best_node)
        lineage_edges = set(zip(path, path[1:]))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        lineage_edges = set()

    # 3) Prepare edge coordinates
    edge_inc_x, edge_inc_y = [], []
    edge_dec_x, edge_dec_y = [], []
    edge_same_x, edge_same_y = [], []
    # lineage pools
    lin_inc_x, lin_inc_y = [], []
    lin_dec_x, lin_dec_y = [], []
    lin_same_x, lin_same_y = [], []

    for parent, child in graph.edges():
        x0, y0 = pos[parent]
        x1, y1 = pos[child]
        p, c = scores[parent], scores[child]

        if (parent, child) in lineage_edges:
            # Thicker but colored the same
            if c > p:
                lin_inc_x.extend([x0, x1, None]); lin_inc_y.extend([y0, y1, None])
            elif c < p:
                lin_dec_x.extend([x0, x1, None]); lin_dec_y.extend([y0, y1, None])
            else:
                lin_same_x.extend([x0, x1, None]); lin_same_y.extend([y0, y1, None])
            continue

        # Normal thin edges
        if c > p:
            edge_inc_x.extend([x0, x1, None]); edge_inc_y.extend([y0, y1, None])
        elif c < p:
            edge_dec_x.extend([x0, x1, None]); edge_dec_y.extend([y0, y1, None])
        else:
            edge_same_x.extend([x0, x1, None]); edge_same_y.extend([y0, y1, None])

    # 4) Build traces
    edge_inc_trace = go.Scatter(x=edge_inc_x, y=edge_inc_y,
        # line=dict(width=1, color="#0F9D58"), hoverinfo="none", mode="lines")
        line=dict(width=1, color="black"), hoverinfo="none", mode="lines")
    edge_dec_trace = go.Scatter(x=edge_dec_x, y=edge_dec_y,
        # line=dict(width=1, color="#DB4437"), hoverinfo="none", mode="lines")
        line=dict(width=1, color="black"), hoverinfo="none", mode="lines")
    edge_same_trace = go.Scatter(x=edge_same_x, y=edge_same_y,
        # line=dict(width=1, color="grey"),   hoverinfo="none", mode="lines")
        line=dict(width=1, color="black"), hoverinfo="none", mode="lines")

    # Thicker lineage traces
    lin_inc_trace = go.Scatter(x=lin_inc_x, y=lin_inc_y,
        # line=dict(width=5, color="#0F9D58"), hoverinfo="none", mode="lines")
        line=dict(width=5, color="black"), hoverinfo="none", mode="lines")
    lin_dec_trace = go.Scatter(x=lin_dec_x, y=lin_dec_y,
        # line=dict(width=5, color="#DB4437"), hoverinfo="none", mode="lines")
        line=dict(width=5, color="black"), hoverinfo="none", mode="lines")
    lin_same_trace = go.Scatter(x=lin_same_x, y=lin_same_y,
        # line=dict(width=5, color="grey"),   hoverinfo="none", mode="lines")
        line=dict(width=5, color="black"), hoverinfo="none", mode="lines")

    # 5) Prepare nodes (same as before)
    node_x, node_y = [], []
    node_text, node_scores, hover_texts, node_border_color = [], [], [], []
    for node, data in graph.nodes(data=True):
        x, y = pos[node]
        node_x.append(x); node_y.append(y)
        node_scores.append(data["score"])
        node_text.append(str(data["index"]))
        hover_texts.append(
            f"Run ID: {data['run_id']}<br>"
            f"{colorbar_title}: {data['score']}<br>"
            f"Eval Quantity: {data['eval_quantity']}<br>"
            f"Compiled: {data['compiled']}<br>"
            f"Archived: {data['archived']}"
        )
        if data["eval_quantity"] == EvalQuantity.SMALL:
            node_border_color.append("#ff0000")
        elif data["eval_quantity"] == EvalQuantity.MED:
            node_border_color.append("#F4B400")
        else:
            node_border_color.append("#0F9D58")

    lowest, highest = min(node_scores), max(node_scores)
    cmin_val = math.floor(lowest * 10) / 10
    cmax_val = math.ceil(highest * 10) / 10

    node_symbols = ["star" if n == best_node else "circle" for n in graph.nodes()]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        hoverinfo="text",
        text=node_text,
        hovertext=hover_texts,
        marker=dict(
            size=30,
            color=node_scores,
            symbol=node_symbols,
            colorscale=[
                [0.0, "#122240"],
                [0.5, "#0F9D58"],
                [1.0, "#FFE800"]
            ],
            cmin=cmin_val,
            cmax=cmax_val,
            # cmax=0.5,
            showscale=True,
            colorbar=dict(
                x=1.02, y=0.5, lenmode='fraction', len=0.9,
                thickness=15, tickfont=dict(size=25), titlefont=dict(size=25),
            ),
            line=dict(width=3, color=node_border_color),
        ),
        textfont=dict(size=12, color="white"),
    )

    # 6) Assemble and save; draw thick lineage on top
    fig = go.Figure(data=[
        edge_inc_trace, edge_dec_trace, edge_same_trace,
        lin_inc_trace, lin_dec_trace, lin_same_trace,
        node_trace
    ])
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    fig.write_html(html_path)
    print(f"Saved interactive visualization to {html_path}")
    svg_path = html_path.replace('.html', '.svg')
    if 'halluc' in colorbar_title.lower():
        fig.write_image(svg_path, width=2200, height=800)
    else:
        fig.write_image(svg_path, width=1100, height=800)
    print(f"Saved static visualization to {svg_path}")


def visualize_experiment_run(dgm_dir, archives, metadata_name="metadata.json"):
    """
    Visualize the experiment run as a directed tree-like graph (using accuracy_score).
    """
    graph, pos = build_graph(dgm_dir, archives, score_func=get_performance_score, metadata_name=metadata_name)

    # Decide on output HTML name
    if metadata_name == "metadata_new.json":
        html_path = os.path.join(dgm_dir, "dgm_tree_new.html")
    else:
        html_path = os.path.join(dgm_dir, "dgm_tree.html")

    create_plotly_figure(graph, pos, html_path, colorbar_title="Score")


def visualize_experiment_run_halluc(dgm_dir, archives, metadata_name="metadata.json"):
    """
    Visualize the experiment run as a directed tree-like graph (using the
    solved_halluc_score + percent_toolutilized if solved=1).
    The final range of this metric is [0, 2], but if compiled=False => 0.0
    """
    graph, pos = build_graph(dgm_dir, archives, score_func=get_hallucination_score, metadata_name=metadata_name)

    # Decide on output HTML name
    if metadata_name == "metadata_new.json":
        html_path = os.path.join(dgm_dir, "dgm_tree_halluc_new.html")
    else:
        html_path = os.path.join(dgm_dir, "dgm_tree_halluc.html")

    create_plotly_figure(graph, pos, html_path, colorbar_title="Halluc Score")


def get_evalswe_command(dgm_dir, node_id):
    """
    Generate the command to evaluate a node on the SWE-bench dataset.
    (Note: This does not depend on metadata naming.)
    """
    root_dir = os.path.abspath("./")  # should be the root of this repo
    patch_paths = get_model_patch_paths(root_dir, dgm_dir, node_id)
    model_patch_paths = f"\"{','.join(patch_paths)}\""
    model_name_or_path = f"dgmnode_{node_id}"
    command = (
        "python test_swebench.py --full_eval --num_samples 50 "
        f"--model_patch_paths {model_patch_paths} "
        f"--model_name_or_path {model_name_or_path}\n"
    )
    return command


def analyse_experiment_run(dgm_dir, archives, metadata_name="metadata.json"):
    """
    Analyse the experiment run (using accuracy_score) and print some statistics.
    """
    compiled_runs = []

    # Collect (node_id, score) for all compiled children
    for archive in archives:
        children = archive.get("children", [])
        children_compiled = archive.get("children_compiled", [])
        for child_node_id in children:
            if child_node_id in children_compiled:
                score = get_performance_score(dgm_dir, child_node_id, metadata_name=metadata_name)
                compiled_runs.append((child_node_id, score))

    # Sort by score descending
    compiled_runs.sort(key=lambda x: x[1], reverse=True)

    # Compute basic statistics
    num_compiled = len(compiled_runs)
    if num_compiled > 0:
        best_score = compiled_runs[0][1]
        worst_score = compiled_runs[-1][1]
        avg_score = sum(score for _, score in compiled_runs) / num_compiled
    else:
        best_score = None
        worst_score = None
        avg_score = None

    # Prepare the analysis string
    analysis_str = "=== Experiment Run Analysis (Accuracy Score) ===\n"
    analysis_str += f"Number of compiled runs: {num_compiled}\n"
    if num_compiled > 0:
        analysis_str += f"Highest score: {best_score}\n"
        analysis_str += f"Lowest score:  {worst_score}\n"
        analysis_str += f"Average score: {round(avg_score, 2)}\n"

    analysis_str += "\nCommands to eval highest scoring runs on SWE-Bench:\n"
    if num_compiled > 0:
        highest_scored = [node_id for node_id, score in compiled_runs if score == best_score]
        for node_id in highest_scored:
            analysis_str += f"{node_id}: {get_evalswe_command(dgm_dir, node_id)}"

    analysis_str += "\nCompiled runs sorted by score (descending):\n"
    for node_id, score in compiled_runs:
        analysis_str += f"  {node_id}: {score}\n"
    analysis_str += "================================\n"

    # Decide on the analysis file name
    if metadata_name == "metadata_new.json":
        analysis_filename = "dgm_analysis_new.txt"
    else:
        analysis_filename = "dgm_analysis.txt"

    analysis_path = os.path.join(dgm_dir, analysis_filename)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis_str)

    # Print the analysis string
    print(analysis_str)
    print(f"Analysis saved to {analysis_path}")


def analyse_experiment_run_halluc(dgm_dir, archives, metadata_name="metadata.json"):
    """
    Analyse the experiment run (using solved_halluc_score + percent_toolutilized if solved=1)
    and print some statistics.
    """
    compiled_runs = []

    # Collect (node_id, "halluc+tool" score) for all children,
    # BUT if a node is not compiled, the score is forced to 0.0
    for archive in archives:
        children = archive.get("children", [])
        children_compiled = archive.get("children_compiled", [])
        for child_node_id in children:
            if child_node_id in children_compiled:
                halluc_score = get_hallucination_score(dgm_dir, child_node_id, metadata_name=metadata_name)
            else:
                halluc_score = 0.0
            compiled_runs.append((child_node_id, halluc_score))

    # Sort by halluc_score descending
    compiled_runs.sort(key=lambda x: x[1], reverse=True)

    # Compute basic statistics
    num_compiled = len(compiled_runs)
    if num_compiled > 0:
        best_score = compiled_runs[0][1]
        worst_score = compiled_runs[-1][1]
        avg_score = sum(score for _, score in compiled_runs) / num_compiled
    else:
        best_score = None
        worst_score = None
        avg_score = None

    # Prepare the analysis string
    analysis_str = "=== Experiment Run Analysis (Hallucination Score + Tool Util) ===\n"
    analysis_str += f"Number of compiled runs: {num_compiled}\n"
    if num_compiled > 0:
        analysis_str += f"Highest final halluc score: {best_score}\n"
        analysis_str += f"Lowest final halluc score:  {worst_score}\n"
        analysis_str += f"Average final halluc score: {round(avg_score, 2)}\n"

    analysis_str += "\nCommands to eval highest scoring runs on SWE-Bench:\n"
    if num_compiled > 0:
        highest_scored = [node_id for node_id, score in compiled_runs if score >= 1.5]
        for node_id in highest_scored:
            analysis_str += f"{node_id}: {get_evalswe_command(dgm_dir, node_id)}"

    analysis_str += "\nCompiled runs sorted by final halluc score (descending):\n"
    for node_id, score in compiled_runs:
        analysis_str += f"  {node_id}: {score}\n"
    analysis_str += "================================\n"

    # Decide on the halluc analysis file name
    if metadata_name == "metadata_new.json":
        analysis_filename = "dgm_analysis_halluc_new.txt"
    else:
        analysis_filename = "dgm_analysis_halluc.txt"

    analysis_path = os.path.join(dgm_dir, analysis_filename)
    with open(analysis_path, "w", encoding='utf-8') as f:
        f.write(analysis_str)

    # Print the analysis string
    print(analysis_str)
    print(f"Analysis saved to {analysis_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize and analyze DGM archive.")
    parser.add_argument("--path", type=str, required=True, help="Path to the DGM run.")
    parser.add_argument("--halluc", action="store_true", help="Plot hallucination scores too.")
    parser.add_argument("--metadata_new", action="store_true", help="Use metadata_new.json instead of metadata.json (and save plots and analyses as *_new.*).")
    parser.add_argument("--trunc_gens", type=int, default=0, help="Truncate the number of iterations to plot (0 = no truncation).")
    args = parser.parse_args()

    dgm_dir = args.path

    # Decide which metadata file to use
    if args.metadata_new:
        metadata_name = "metadata_new.json"
    else:
        metadata_name = "metadata.json"

    # Load the global archives (these are read from dgm_metadata.jsonl, not from the node metadata)
    archives = load_dgm_metadata(os.path.join(dgm_dir, "dgm_metadata.jsonl"))
    archives = archives[:args.trunc_gens] if args.trunc_gens > 0 else archives

    # Standard visualization & analysis (using accuracy_score)
    visualize_experiment_run(dgm_dir, archives, metadata_name=metadata_name)
    analyse_experiment_run(dgm_dir, archives, metadata_name=metadata_name)

    # Hallucination visualization & analysis (using solved_halluc_score + percent_toolutilized)
    if args.halluc:
        visualize_experiment_run_halluc(dgm_dir, archives, metadata_name=metadata_name)
        analyse_experiment_run_halluc(dgm_dir, archives, metadata_name=metadata_name)


if __name__ == "__main__":
    main()