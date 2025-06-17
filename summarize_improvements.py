#!/usr/bin/env python3
"""
Script to summarize improvements made during a DGM run using SWE-bench results.
This provides a comprehensive analysis of what the Darwin Gödel Machine accomplished.
"""

import argparse
import json
import os
from pathlib import Path


def load_metadata(metadata_path):
    """Load metadata from a JSON file."""
    if not os.path.exists(metadata_path):
        return None
    with open(metadata_path, 'r') as f:
        return json.load(f)


def load_dgm_metadata(dgm_metadata_path):
    """Load DGM metadata from JSONL file."""
    archives = []
    if os.path.exists(dgm_metadata_path):
        with open(dgm_metadata_path, 'r') as f:
            content = f.read().strip()
            # Handle case where file contains multiple JSON objects separated by newlines
            # but not necessarily one per line (could be formatted JSON)
            if content:
                # Try to parse as single JSON first
                try:
                    archives = [json.loads(content)]
                except json.JSONDecodeError:
                    # If that fails, try to split by } and parse each part
                    json_objects = []
                    current_obj = ""
                    brace_count = 0
                    
                    for char in content:
                        current_obj += char
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Complete JSON object
                                try:
                                    obj = json.loads(current_obj.strip())
                                    json_objects.append(obj)
                                    current_obj = ""
                                except json.JSONDecodeError:
                                    pass
                    archives = json_objects
    return archives


def get_performance_score(dgm_dir, node_id):
    """Get the accuracy score for a node."""
    metadata_path = os.path.join(dgm_dir, node_id, "metadata.json")
    metadata = load_metadata(metadata_path)
    if metadata and "overall_performance" in metadata:
        return metadata["overall_performance"].get("accuracy_score", 0.0)
    return 0.0


def get_resolved_tasks(dgm_dir, node_id):
    """Get the list of resolved task IDs for a node."""
    metadata_path = os.path.join(dgm_dir, node_id, "metadata.json")
    metadata = load_metadata(metadata_path)
    if metadata and "overall_performance" in metadata:
        return metadata["overall_performance"].get("total_resolved_ids", [])
    return []


def get_total_tasks(dgm_dir, node_id):
    """Get the total number of tasks evaluated for a node."""
    metadata_path = os.path.join(dgm_dir, node_id, "metadata.json")
    metadata = load_metadata(metadata_path)
    if metadata and "overall_performance" in metadata:
        return metadata["overall_performance"].get("total_submitted_instances", 0)
    return 0


def get_improvement_description(dgm_dir, node_id):
    """Get the improvement description from metadata."""
    metadata_path = os.path.join(dgm_dir, node_id, "metadata.json")
    metadata = load_metadata(metadata_path)
    if metadata:
        return metadata.get("entry", "Unknown improvement")
    return "Unknown improvement"


def get_problem_statement(dgm_dir, node_id):
    """Get the problem statement that was being addressed."""
    metadata_path = os.path.join(dgm_dir, node_id, "metadata.json")
    metadata = load_metadata(metadata_path)
    if metadata:
        return metadata.get("problem_statement", "No problem statement available")
    return "No problem statement available"


def analyze_improvements(dgm_dir):
    """Analyze all improvements made during the DGM run."""
    
    # Load DGM metadata
    dgm_metadata_path = os.path.join(dgm_dir, "dgm_metadata.jsonl")
    archives = load_dgm_metadata(dgm_metadata_path)
    
    # Get baseline performance
    baseline_score = get_performance_score(dgm_dir, "initial")
    baseline_resolved = get_resolved_tasks(dgm_dir, "initial")
    baseline_total = get_total_tasks(dgm_dir, "initial")
    
    print("=" * 80)
    print("DARWIN GÖDEL MACHINE - IMPROVEMENT SUMMARY")
    print("=" * 80)
    print()
    
    print(f"📊 BASELINE PERFORMANCE (Initial Agent)")
    print(f"   • SWE-bench Accuracy: {baseline_score:.1%} ({len(baseline_resolved)}/{baseline_total} tasks)")
    print(f"   • Resolved Tasks: {len(baseline_resolved)}")
    print()
    
    # Analyze each generation
    all_attempts = []
    compiled_attempts = []
    best_score = baseline_score
    best_node = "initial"
    
    for generation_idx, archive in enumerate(archives):
        print(f"🧬 GENERATION {generation_idx}")
        children = archive.get("children", [])
        children_compiled = archive.get("children_compiled", [])
        
        print(f"   • Self-improvement attempts: {len(children)}")
        print(f"   • Successfully compiled: {len(children_compiled)}")
        
        # Analyze each child
        for child_id in children:
            improvement_type = get_improvement_description(dgm_dir, child_id)
            compiled = child_id in children_compiled
            
            if compiled:
                score = get_performance_score(dgm_dir, child_id)
                resolved = get_resolved_tasks(dgm_dir, child_id)
                total = get_total_tasks(dgm_dir, child_id)
                
                attempt_info = {
                    'node_id': child_id,
                    'generation': generation_idx,
                    'improvement_type': improvement_type,
                    'score': score,
                    'resolved_count': len(resolved),
                    'total_tasks': total,
                    'resolved_tasks': resolved,
                    'compiled': True
                }
                compiled_attempts.append(attempt_info)
                
                if score > best_score:
                    best_score = score
                    best_node = child_id
                
                print(f"     ✅ {child_id}: {improvement_type}")
                print(f"        → SWE-bench: {score:.1%} ({len(resolved)}/{total} tasks)")
                
                # Show improvement over baseline
                if score > baseline_score:
                    improvement = score - baseline_score
                    print(f"        → 📈 IMPROVEMENT: +{improvement:.1%} over baseline")
                elif score < baseline_score:
                    decline = baseline_score - score
                    print(f"        → 📉 Decline: -{decline:.1%} from baseline")
                else:
                    print(f"        → ➡️  No change from baseline")
            else:
                attempt_info = {
                    'node_id': child_id,
                    'generation': generation_idx,
                    'improvement_type': improvement_type,
                    'compiled': False
                }
                print(f"     ❌ {child_id}: {improvement_type} (compilation failed)")
            
            all_attempts.append(attempt_info)
        print()
    
    # Summary statistics
    print("📈 OVERALL RESULTS")
    print(f"   • Total self-improvement attempts: {len(all_attempts)}")
    print(f"   • Successfully compiled attempts: {len(compiled_attempts)}")
    print(f"   • Compilation success rate: {len(compiled_attempts)/len(all_attempts):.1%}")
    print()
    
    if compiled_attempts:
        scores = [attempt['score'] for attempt in compiled_attempts]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        
        print(f"   • Best performance achieved: {max_score:.1%}")
        print(f"   • Average performance: {avg_score:.1%}")
        print(f"   • Performance range: {min_score:.1%} - {max_score:.1%}")
        
        if max_score > baseline_score:
            total_improvement = max_score - baseline_score
            print(f"   • 🎯 NET IMPROVEMENT: +{total_improvement:.1%} over baseline")
        else:
            print(f"   • ⚠️  No improvement achieved over baseline")
    
    print()
    
    # Improvement types analysis
    improvement_types = {}
    for attempt in all_attempts:
        imp_type = attempt['improvement_type']
        if imp_type not in improvement_types:
            improvement_types[imp_type] = {'total': 0, 'compiled': 0, 'scores': []}
        
        improvement_types[imp_type]['total'] += 1
        if attempt['compiled']:
            improvement_types[imp_type]['compiled'] += 1
            improvement_types[imp_type]['scores'].append(attempt['score'])
    
    print("🔧 IMPROVEMENT STRATEGIES ATTEMPTED")
    for imp_type, stats in improvement_types.items():
        success_rate = stats['compiled'] / stats['total'] if stats['total'] > 0 else 0
        avg_score = sum(stats['scores']) / len(stats['scores']) if stats['scores'] else 0
        
        print(f"   • {imp_type}:")
        print(f"     - Attempts: {stats['total']}")
        print(f"     - Success rate: {success_rate:.1%}")
        if stats['scores']:
            print(f"     - Average performance: {avg_score:.1%}")
            best_for_type = max(stats['scores'])
            if best_for_type > baseline_score:
                print(f"     - Best improvement: +{best_for_type - baseline_score:.1%}")
    
    print()
    
    # Best performing agent details
    if best_node != "initial":
        print("🏆 BEST PERFORMING AGENT")
        best_resolved = get_resolved_tasks(dgm_dir, best_node)
        best_total = get_total_tasks(dgm_dir, best_node)
        best_improvement_type = get_improvement_description(dgm_dir, best_node)
        
        print(f"   • Node ID: {best_node}")
        print(f"   • Improvement Type: {best_improvement_type}")
        print(f"   • SWE-bench Performance: {best_score:.1%} ({len(best_resolved)}/{best_total} tasks)")
        print(f"   • Improvement over baseline: +{best_score - baseline_score:.1%}")
        
        # Show newly resolved tasks
        newly_resolved = set(best_resolved) - set(baseline_resolved)
        if newly_resolved:
            print(f"   • Newly resolved tasks ({len(newly_resolved)}):")
            for task in sorted(newly_resolved):
                print(f"     - {task}")
        
        # Show problem statement for best improvement
        problem_statement = get_problem_statement(dgm_dir, best_node)
        if problem_statement and problem_statement != "No problem statement available":
            print(f"\n   📋 Problem Statement:")
            # Truncate long problem statements
            if len(problem_statement) > 500:
                print(f"     {problem_statement[:500]}...")
            else:
                print(f"     {problem_statement}")
    else:
        print("🏆 BEST PERFORMING AGENT")
        print("   • No improvements achieved - baseline agent remains best")
    
    print()
    print("=" * 80)
    
    return {
        'baseline_score': baseline_score,
        'best_score': best_score,
        'best_node': best_node,
        'total_attempts': len(all_attempts),
        'compiled_attempts': len(compiled_attempts),
        'improvement_types': improvement_types,
        'all_attempts': all_attempts
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize DGM improvements using SWE-bench results")
    parser.add_argument("--path", type=str, required=True, help="Path to the DGM run directory")
    parser.add_argument("--save", action="store_true", help="Save summary to a text file")
    args = parser.parse_args()
    
    dgm_dir = args.path
    
    if not os.path.exists(dgm_dir):
        print(f"Error: Directory {dgm_dir} does not exist")
        return
    
    # Analyze improvements
    results = analyze_improvements(dgm_dir)
    
    # Optionally save to file
    if args.save:
        import sys
        from io import StringIO
        
        # Capture the output
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        # Re-run analysis to capture output
        analyze_improvements(dgm_dir)
        
        # Restore stdout
        sys.stdout = old_stdout
        
        # Save to file
        summary_path = os.path.join(dgm_dir, "improvement_summary.txt")
        with open(summary_path, 'w') as f:
            f.write(captured_output.getvalue())
        
        print(f"\n💾 Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()