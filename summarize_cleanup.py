#!/usr/bin/env python3
"""
Comprehensive cleanup and summarization script for Darwin Gödel Machine (DGM).

This script consolidates all post-run operations:
1. Summarizes improvements made during DGM runs
2. Cleans up Docker containers and images
3. Removes temporary files
4. Generates comprehensive reports
5. Auto-detects latest output directories

Usage:
    python cleanup_and_summarize.py                    # Auto-find latest output
    python cleanup_and_summarize.py --path <dir>       # Specific directory
    python cleanup_and_summarize.py --all              # Clean all DGM outputs
    python cleanup_and_summarize.py --docker-only      # Only Docker cleanup
    python cleanup_and_summarize.py --summary-only     # Only generate summary
"""

import argparse
import docker
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import existing utilities
try:
    from polyglot.docker_utils import cleanup_container, remove_image
except ImportError:
    print("Warning: Could not import polyglot.docker_utils")
    cleanup_container = None
    remove_image = None


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
    
    # Analyze each generation
    all_attempts = []
    compiled_attempts = []
    best_score = baseline_score
    best_node = "initial"
    
    for generation_idx, archive in enumerate(archives):
        children = archive.get("children", [])
        children_compiled = archive.get("children_compiled", [])
        
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
            else:
                attempt_info = {
                    'node_id': child_id,
                    'generation': generation_idx,
                    'improvement_type': improvement_type,
                    'compiled': False
                }
            
            all_attempts.append(attempt_info)
    
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
    
    return {
        'baseline_score': baseline_score,
        'best_score': best_score,
        'best_node': best_node,
        'total_attempts': len(all_attempts),
        'compiled_attempts': len(compiled_attempts),
        'improvement_types': improvement_types,
        'all_attempts': all_attempts,
        'baseline_resolved': baseline_resolved,
        'baseline_total': baseline_total
    }


class DGMCleanupManager:
    """Comprehensive cleanup and summarization manager for DGM."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.docker_client = None
        self.log_entries = []
        self.start_time = time.time()
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.log("✅ Docker client initialized successfully")
        except Exception as e:
            self.log(f"⚠️  Warning: Could not initialize Docker client: {e}")
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_entries.append(log_entry)
        if self.verbose:
            print(log_entry)
    
    def find_dgm_outputs(self) -> List[Path]:
        """Find all DGM output directories."""
        output_dir = Path("output_dgm")
        
        if not output_dir.exists():
            return []
        
        # Find directories that start with "20" (timestamp format)
        timestamp_dirs = [d for d in output_dir.iterdir()
                         if d.is_dir() and d.name.startswith("20")]
        
        return sorted(timestamp_dirs, key=lambda x: x.name, reverse=True)
    
    def find_latest_output(self) -> Optional[Path]:
        """Find the latest DGM output directory."""
        outputs = self.find_dgm_outputs()
        return outputs[0] if outputs else None
    
    def summarize_single_run(self, dgm_path: Path) -> Dict:
        """Generate summary for a single DGM run."""
        self.log(f"📊 Analyzing DGM run: {dgm_path.name}")
        
        if not dgm_path.exists():
            self.log(f"❌ Error: Path {dgm_path} does not exist")
            return {}
        
        try:
            # Run analysis using integrated function
            results = analyze_improvements(str(dgm_path))
            self.log("✅ Summary generated successfully")
            return results
            
        except Exception as e:
            self.log(f"❌ Error generating summary: {e}")
            return {}
    
    def cleanup_docker_resources(self, aggressive: bool = False) -> Dict[str, int]:
        """Clean up Docker containers and images related to DGM."""
        self.log("🐳 Starting Docker cleanup...")
        
        if not self.docker_client:
            self.log("⚠️  Skipping Docker cleanup - client not available")
            return {"containers_removed": 0, "images_removed": 0, "errors": 0}
        
        stats = {"containers_removed": 0, "images_removed": 0, "errors": 0}
        
        try:
            # Clean up containers
            containers = self.docker_client.containers.list(all=True)
            dgm_containers = []
            
            for container in containers:
                name = container.name.lower()
                if any(keyword in name for keyword in ['dgm', 'swe', 'eval', 'polyglot']):
                    dgm_containers.append(container)
            
            self.log(f"Found {len(dgm_containers)} DGM-related containers")
            
            for container in dgm_containers:
                try:
                    self.log(f"Removing container: {container.name}")
                    if cleanup_container:
                        cleanup_container(self.docker_client, container, logger="quiet")
                    else:
                        # Fallback cleanup
                        if container.status == 'running':
                            container.stop(timeout=10)
                        container.remove(force=True)
                    stats["containers_removed"] += 1
                except Exception as e:
                    self.log(f"Failed to remove container {container.name}: {e}")
                    stats["errors"] += 1
            
            # Clean up images
            images = self.docker_client.images.list(all=True)
            dgm_images = []
            
            for image in images:
                if image.tags:
                    for tag in image.tags:
                        if any(keyword in tag.lower() for keyword in ['dgm', 'swe', 'sweb', 'eval', 'polyglot']):
                            dgm_images.append(image)
                            break
                elif aggressive:
                    # Include untagged images in aggressive mode
                    dgm_images.append(image)
            
            self.log(f"Found {len(dgm_images)} DGM-related images")
            
            for image in dgm_images:
                try:
                    image_name = image.tags[0] if image.tags else image.id[:12]
                    self.log(f"Removing image: {image_name}")
                    if remove_image:
                        remove_image(self.docker_client, image.id, logger="quiet")
                    else:
                        # Fallback removal
                        self.docker_client.images.remove(image.id, force=True)
                    stats["images_removed"] += 1
                except Exception as e:
                    self.log(f"Failed to remove image: {e}")
                    stats["errors"] += 1
            
            self.log(f"✅ Docker cleanup complete: {stats['containers_removed']} containers, {stats['images_removed']} images removed")
            
        except Exception as e:
            self.log(f"❌ Error during Docker cleanup: {e}")
            stats["errors"] += 1
        
        return stats
    
    def cleanup_temporary_files(self, paths: List[Path]) -> Dict[str, int]:
        """Clean up temporary files in specified paths."""
        self.log("🗂️  Starting temporary file cleanup...")
        
        stats = {"files_removed": 0, "dirs_removed": 0, "errors": 0}
        
        temp_patterns = [
            "*.tmp", "*.temp", "*_temp", "temp_*",
            ".cache", "__pycache__", "*.pyc", "*.pyo",
            "*.log", ".DS_Store", "Thumbs.db"
        ]
        
        for path in paths:
            if not path.exists():
                continue
                
            self.log(f"Cleaning temporary files in: {path}")
            
            for pattern in temp_patterns:
                try:
                    for item in path.rglob(pattern):
                        try:
                            if item.is_file():
                                item.unlink()
                                stats["files_removed"] += 1
                            elif item.is_dir() and pattern in ["__pycache__", ".cache"]:
                                shutil.rmtree(item)
                                stats["dirs_removed"] += 1
                        except Exception as e:
                            stats["errors"] += 1
                except Exception:
                    pass  # Pattern might not match anything
        
        self.log(f"✅ Temporary file cleanup complete: {stats['files_removed']} files, {stats['dirs_removed']} directories removed")
        return stats
    
    def generate_comprehensive_report(self, summaries: List[Dict], docker_stats: Dict, file_stats: Dict) -> str:
        """Generate a comprehensive cleanup and summary report."""
        self.log("📋 Generating comprehensive report...")
        
        duration = time.time() - self.start_time
        
        lines = [
            "=" * 80,
            "DARWIN GÖDEL MACHINE - COMPREHENSIVE CLEANUP & SUMMARY REPORT",
            "=" * 80,
            "",
            f"🕐 Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"⏱️  Total processing time: {duration:.2f} seconds",
            f"📁 DGM runs analyzed: {len(summaries)}",
            "",
        ]
        
        # Summary of all runs
        if summaries:
            lines.extend([
                "📊 DGM RUNS SUMMARY",
                "-" * 40,
            ])
            
            total_attempts = sum(s.get('total_attempts', 0) for s in summaries)
            total_compiled = sum(s.get('compiled_attempts', 0) for s in summaries)
            best_overall_score = max((s.get('best_score', 0) for s in summaries), default=0)
            avg_baseline = sum(s.get('baseline_score', 0) for s in summaries) / len(summaries)
            
            lines.extend([
                f"• Total improvement attempts across all runs: {total_attempts}",
                f"• Total successfully compiled attempts: {total_compiled}",
                f"• Overall compilation success rate: {total_compiled/total_attempts:.1%}" if total_attempts > 0 else "• No attempts made",
                f"• Best performance achieved: {best_overall_score:.1%}",
                f"• Average baseline performance: {avg_baseline:.1%}",
                "",
            ])
            
            # Individual run details
            lines.extend([
                "📈 INDIVIDUAL RUN DETAILS",
                "-" * 40,
            ])
            
            for i, summary in enumerate(summaries):
                run_name = summary.get('run_name', f'Run {i+1}')
                baseline = summary.get('baseline_score', 0)
                best = summary.get('best_score', 0)
                attempts = summary.get('total_attempts', 0)
                compiled = summary.get('compiled_attempts', 0)
                
                lines.extend([
                    f"🧬 {run_name}:",
                    f"   • Baseline: {baseline:.1%}, Best: {best:.1%}",
                    f"   • Attempts: {attempts}, Compiled: {compiled}",
                ])
                
                if best > baseline:
                    improvement = best - baseline
                    lines.append(f"   • 🎯 Improvement: +{improvement:.1%}")
                else:
                    lines.append(f"   • ⚠️  No improvement achieved")
                
                lines.append("")
        
        # Docker cleanup summary
        lines.extend([
            "🐳 DOCKER CLEANUP SUMMARY",
            "-" * 40,
            f"• Containers removed: {docker_stats.get('containers_removed', 0)}",
            f"• Images removed: {docker_stats.get('images_removed', 0)}",
            f"• Cleanup errors: {docker_stats.get('errors', 0)}",
            "",
        ])
        
        # File cleanup summary
        lines.extend([
            "🗂️  FILE CLEANUP SUMMARY",
            "-" * 40,
            f"• Temporary files removed: {file_stats.get('files_removed', 0)}",
            f"• Temporary directories removed: {file_stats.get('dirs_removed', 0)}",
            f"• File cleanup errors: {file_stats.get('errors', 0)}",
            "",
        ])
        
        # Cleanup log
        lines.extend([
            "📝 DETAILED CLEANUP LOG",
            "-" * 40,
        ])
        
        for log_entry in self.log_entries:
            lines.append(f"  {log_entry}")
        
        lines.extend([
            "",
            "=" * 80,
            ""
        ])
        
        return "\n".join(lines)
    
    def save_report(self, report: str, output_path: Path, filename: str = "comprehensive_cleanup_report.txt"):
        """Save the comprehensive report to a file."""
        report_path = output_path / filename
        try:
            with open(report_path, 'w') as f:
                f.write(report)
            self.log(f"💾 Comprehensive report saved to: {report_path}")
            return report_path
        except Exception as e:
            self.log(f"❌ Failed to save report: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive DGM cleanup and summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python summarize_cleanup.py                        # Auto-find latest output
  python summarize_cleanup.py --path output_dgm/20241201_120000  # Specific run
  python summarize_cleanup.py --all                  # All DGM outputs
  python summarize_cleanup.py --docker-only          # Only Docker cleanup
  python summarize_cleanup.py --summary-only         # Only generate summaries
        """
    )
    
    parser.add_argument("--path", type=str,
                       help="Path to specific DGM run directory")
    parser.add_argument("--all", action="store_true",
                       help="Process all DGM output directories")
    parser.add_argument("--docker-only", action="store_true",
                       help="Only perform Docker cleanup")
    parser.add_argument("--summary-only", action="store_true",
                       help="Only generate summaries, no cleanup")
    parser.add_argument("--no-docker", action="store_true",
                       help="Skip Docker cleanup")
    parser.add_argument("--no-files", action="store_true",
                       help="Skip temporary file cleanup")
    parser.add_argument("--aggressive", action="store_true",
                       help="Aggressive cleanup (includes untagged Docker images)")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress verbose output")
    
    args = parser.parse_args()
    
    # Initialize manager
    manager = DGMCleanupManager(verbose=not args.quiet)
    
    # Determine which directories to process
    dgm_paths = []
    
    if args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"❌ Error: Directory {path} does not exist")
            sys.exit(1)
        dgm_paths = [path]
        
    elif args.all:
        dgm_paths = manager.find_dgm_outputs()
        if not dgm_paths:
            print("❌ Error: No DGM output directories found")
            sys.exit(1)
        manager.log(f"Found {len(dgm_paths)} DGM output directories")
        
    else:
        # Auto-detect latest
        latest = manager.find_latest_output()
        if not latest:
            print("❌ Error: No DGM output directories found")
            print("❌ Make sure you have run DGM_outer.py first")
            sys.exit(1)
        dgm_paths = [latest]
        manager.log(f"Auto-detected latest output: {latest}")
    
    try:
        # Generate summaries
        summaries = []
        if not args.docker_only:
            for path in dgm_paths:
                summary = manager.summarize_single_run(path)
                if summary:
                    summary['run_name'] = path.name
                    summaries.append(summary)
        
        # Docker cleanup
        docker_stats = {"containers_removed": 0, "images_removed": 0, "errors": 0}
        if not args.summary_only and not args.no_docker:
            docker_stats = manager.cleanup_docker_resources(aggressive=args.aggressive)
        
        # File cleanup
        file_stats = {"files_removed": 0, "dirs_removed": 0, "errors": 0}
        if not args.summary_only and not args.no_files:
            file_stats = manager.cleanup_temporary_files(dgm_paths)
        
        # Generate comprehensive report
        if not args.docker_only:
            report = manager.generate_comprehensive_report(summaries, docker_stats, file_stats)
            
            # Save report to the most recent directory
            output_dir = dgm_paths[0] if dgm_paths else Path(".")
            report_path = manager.save_report(report, output_dir)
            
            # Also print summary to console
            if not args.quiet:
                print("\n" + "="*60)
                print("CLEANUP SUMMARY")
                print("="*60)
                print(f"📊 DGM runs processed: {len(summaries)}")
                print(f"🐳 Docker containers removed: {docker_stats['containers_removed']}")
                print(f"🖼️  Docker images removed: {docker_stats['images_removed']}")
                print(f"🗂️  Temporary files removed: {file_stats['files_removed']}")
                if report_path:
                    print(f"📋 Full report saved to: {report_path}")
                print("✅ Cleanup completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()