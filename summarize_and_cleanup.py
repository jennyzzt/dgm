#!/usr/bin/env python3
"""
Summarize and cleanup script for Darwin Gödel Machine (DGM).

This script performs the following tasks after a DGM run:
1. Summarizes the improvements made during the run
2. Cleans up Docker containers and images
3. Generates a comprehensive report
4. Automatically finds latest output if no path specified

Usage:
    python summarize_and_cleanup.py [--path <dgm_output_path>] [options]
    python summarize_and_cleanup.py --auto  # Auto-find latest output
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
from typing import Dict, List, Optional

# Import existing utilities
from summarize_improvements import analyze_improvements
from polyglot.docker_utils import cleanup_container, remove_image, list_images


def find_latest_output_dir():
    """Find the latest DGM output directory."""
    output_dir = Path("output_dgm")
    
    if not output_dir.exists():
        return None
    
    # Find directories that start with "20" (timestamp format)
    timestamp_dirs = [d for d in output_dir.iterdir()
                     if d.is_dir() and d.name.startswith("20")]
    
    if not timestamp_dirs:
        return None
    
    # Return the most recent one
    return max(timestamp_dirs, key=lambda x: x.name)


class DGMPostRunCleanup:
    """Main class for post-run cleanup operations."""
    
    def __init__(self, dgm_path: str, verbose: bool = True):
        self.dgm_path = Path(dgm_path)
        self.verbose = verbose
        self.docker_client = None
        self.cleanup_log = []
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.log("✅ Docker client initialized successfully")
        except Exception as e:
            self.log(f"⚠️  Warning: Could not initialize Docker client: {e}")
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.cleanup_log.append(log_entry)
        if self.verbose:
            print(log_entry)
    
    def summarize_improvements(self) -> Dict:
        """Generate improvement summary using existing functionality."""
        self.log("📊 Generating improvement summary...")
        
        if not self.dgm_path.exists():
            self.log(f"❌ Error: DGM path {self.dgm_path} does not exist")
            return {}
        
        try:
            # Use existing summarize_improvements functionality
            results = analyze_improvements(str(self.dgm_path))
            self.log("✅ Improvement summary generated successfully")
            return results
        except Exception as e:
            self.log(f"❌ Error generating improvement summary: {e}")
            return {}
    
    def cleanup_docker_containers(self) -> Dict[str, int]:
        """Clean up Docker containers related to DGM runs."""
        self.log("🐳 Starting Docker container cleanup...")
        
        if not self.docker_client:
            self.log("⚠️  Skipping Docker cleanup - client not available")
            return {"containers_removed": 0, "containers_failed": 0}
        
        containers_removed = 0
        containers_failed = 0
        
        try:
            # Get all containers (including stopped ones)
            all_containers = self.docker_client.containers.list(all=True)
            dgm_containers = []
            
            # Find DGM-related containers
            for container in all_containers:
                container_name = container.name.lower()
                # Look for containers with DGM-related names
                if any(keyword in container_name for keyword in ['dgm', 'swe', 'eval', 'polyglot']):
                    dgm_containers.append(container)
            
            self.log(f"Found {len(dgm_containers)} DGM-related containers")
            
            # Clean up each container
            for container in dgm_containers:
                try:
                    self.log(f"Cleaning up container: {container.name}")
                    cleanup_container(self.docker_client, container, logger="quiet")
                    containers_removed += 1
                except Exception as e:
                    self.log(f"Failed to cleanup container {container.name}: {e}")
                    containers_failed += 1
            
            self.log(f"✅ Container cleanup complete: {containers_removed} removed, {containers_failed} failed")
            
        except Exception as e:
            self.log(f"❌ Error during container cleanup: {e}")
        
        return {"containers_removed": containers_removed, "containers_failed": containers_failed}
    
    def cleanup_docker_images(self, aggressive: bool = False) -> Dict[str, int]:
        """Clean up Docker images related to DGM runs."""
        self.log("🖼️  Starting Docker image cleanup...")
        
        if not self.docker_client:
            self.log("⚠️  Skipping Docker image cleanup - client not available")
            return {"images_removed": 0, "images_failed": 0}
        
        images_removed = 0
        images_failed = 0
        
        try:
            # Get all images
            all_images = self.docker_client.images.list(all=True)
            dgm_images = []
            
            # Find DGM-related images
            for image in all_images:
                image_tags = image.tags
                if image_tags:
                    for tag in image_tags:
                        tag_lower = tag.lower()
                        # Look for images with DGM-related tags
                        if any(keyword in tag_lower for keyword in ['dgm', 'swe', 'sweb', 'eval', 'polyglot']):
                            dgm_images.append(image)
                            break
                elif aggressive:
                    # Include untagged images if aggressive cleanup
                    dgm_images.append(image)
            
            self.log(f"Found {len(dgm_images)} DGM-related images")
            
            # Clean up each image
            for image in dgm_images:
                try:
                    image_id = image.id[:12]  # Short ID for logging
                    tags = image.tags[0] if image.tags else image_id
                    self.log(f"Removing image: {tags}")
                    remove_image(self.docker_client, image.id, logger="quiet")
                    images_removed += 1
                except Exception as e:
                    self.log(f"Failed to remove image {tags}: {e}")
                    images_failed += 1
            
            self.log(f"✅ Image cleanup complete: {images_removed} removed, {images_failed} failed")
            
        except Exception as e:
            self.log(f"❌ Error during image cleanup: {e}")
        
        return {"images_removed": images_removed, "images_failed": images_failed}
    
    def cleanup_temporary_files(self) -> Dict[str, int]:
        """Clean up temporary files and directories."""
        self.log("🗂️  Starting temporary file cleanup...")
        
        files_removed = 0
        dirs_removed = 0
        
        try:
            # Look for common temporary directories and files
            temp_patterns = [
                "*.tmp",
                "*.temp",
                "*_temp",
                "temp_*",
                ".cache",
                "__pycache__",
                "*.pyc",
                "*.log"
            ]
            
            # Clean up in DGM directory
            for pattern in temp_patterns:
                for item in self.dgm_path.rglob(pattern):
                    try:
                        if item.is_file():
                            item.unlink()
                            files_removed += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            dirs_removed += 1
                    except Exception as e:
                        self.log(f"Failed to remove {item}: {e}")
            
            self.log(f"✅ Temporary file cleanup complete: {files_removed} files, {dirs_removed} directories removed")
            
        except Exception as e:
            self.log(f"❌ Error during temporary file cleanup: {e}")
        
        return {"files_removed": files_removed, "dirs_removed": dirs_removed}
    
    def generate_cleanup_report(self, summary_results: Dict, docker_stats: Dict, file_stats: Dict) -> str:
        """Generate a comprehensive cleanup report."""
        self.log("📋 Generating cleanup report...")
        
        report_lines = [
            "=" * 80,
            "DARWIN GÖDEL MACHINE - POST-RUN CLEANUP REPORT",
            "=" * 80,
            "",
            f"🕐 Cleanup completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📁 DGM run path: {self.dgm_path}",
            "",
            "📊 IMPROVEMENT SUMMARY",
            "-" * 40,
        ]
        
        if summary_results:
            baseline_score = summary_results.get('baseline_score', 0)
            best_score = summary_results.get('best_score', 0)
            total_attempts = summary_results.get('total_attempts', 0)
            compiled_attempts = summary_results.get('compiled_attempts', 0)
            
            report_lines.extend([
                f"• Baseline performance: {baseline_score:.1%}",
                f"• Best performance achieved: {best_score:.1%}",
                f"• Total improvement attempts: {total_attempts}",
                f"• Successfully compiled attempts: {compiled_attempts}",
                f"• Compilation success rate: {compiled_attempts/total_attempts:.1%}" if total_attempts > 0 else "• No attempts made",
                ""
            ])
            
            if best_score > baseline_score:
                improvement = best_score - baseline_score
                report_lines.append(f"🎯 NET IMPROVEMENT: +{improvement:.1%}")
            else:
                report_lines.append("⚠️  No improvement achieved over baseline")
        else:
            report_lines.append("❌ Could not generate improvement summary")
        
        report_lines.extend([
            "",
            "🐳 DOCKER CLEANUP",
            "-" * 40,
            f"• Containers removed: {docker_stats.get('containers_removed', 0)}",
            f"• Container cleanup failures: {docker_stats.get('containers_failed', 0)}",
            f"• Images removed: {docker_stats.get('images_removed', 0)}",
            f"• Image cleanup failures: {docker_stats.get('images_failed', 0)}",
            "",
            "🗂️  FILE CLEANUP",
            "-" * 40,
            f"• Temporary files removed: {file_stats.get('files_removed', 0)}",
            f"• Temporary directories removed: {file_stats.get('dirs_removed', 0)}",
            "",
            "📝 CLEANUP LOG",
            "-" * 40,
        ])
        
        # Add cleanup log entries
        for log_entry in self.cleanup_log:
            report_lines.append(f"  {log_entry}")
        
        report_lines.extend([
            "",
            "=" * 80,
            ""
        ])
        
        return "\n".join(report_lines)
    
    def save_report(self, report: str, filename: str = "cleanup_report.txt"):
        """Save the cleanup report to a file."""
        report_path = self.dgm_path / filename
        try:
            with open(report_path, 'w') as f:
                f.write(report)
            self.log(f"💾 Cleanup report saved to: {report_path}")
        except Exception as e:
            self.log(f"❌ Failed to save cleanup report: {e}")
    
    def run_full_cleanup(self, cleanup_docker: bool = True, cleanup_images: bool = True, 
                        aggressive_images: bool = False, cleanup_files: bool = True) -> Dict:
        """Run the complete cleanup process."""
        self.log("🚀 Starting DGM post-run cleanup...")
        start_time = time.time()
        
        # Step 1: Generate improvement summary
        summary_results = self.summarize_improvements()
        
        # Step 2: Docker cleanup
        docker_stats = {"containers_removed": 0, "containers_failed": 0, "images_removed": 0, "images_failed": 0}
        if cleanup_docker:
            container_stats = self.cleanup_docker_containers()
            docker_stats.update(container_stats)
            
            if cleanup_images:
                image_stats = self.cleanup_docker_images(aggressive=aggressive_images)
                docker_stats.update(image_stats)
        
        # Step 3: File cleanup
        file_stats = {"files_removed": 0, "dirs_removed": 0}
        if cleanup_files:
            file_stats = self.cleanup_temporary_files()
        
        # Step 4: Generate and save report
        report = self.generate_cleanup_report(summary_results, docker_stats, file_stats)
        self.save_report(report)
        
        end_time = time.time()
        duration = end_time - start_time
        
        self.log(f"✅ Cleanup completed in {duration:.2f} seconds")
        
        return {
            "summary_results": summary_results,
            "docker_stats": docker_stats,
            "file_stats": file_stats,
            "duration": duration
        }


def main():
    parser = argparse.ArgumentParser(description="DGM summarize and cleanup")
    parser.add_argument("--path", type=str,
                       help="Path to the DGM run directory (auto-detects latest if not provided)")
    parser.add_argument("--auto", action="store_true",
                       help="Automatically find and use the latest output directory")
    parser.add_argument("--no-docker", action="store_true",
                       help="Skip Docker container cleanup")
    parser.add_argument("--no-images", action="store_true",
                       help="Skip Docker image cleanup")
    parser.add_argument("--aggressive-images", action="store_true",
                       help="Aggressively remove untagged images")
    parser.add_argument("--no-files", action="store_true",
                       help="Skip temporary file cleanup")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress verbose output")
    
    args = parser.parse_args()
    
    # Determine the path to use
    dgm_path = None
    
    if args.path:
        dgm_path = args.path
        if not os.path.exists(dgm_path):
            print(f"❌ Error: Directory {dgm_path} does not exist")
            sys.exit(1)
    else:
        # Auto-detect latest output directory
        if not args.quiet:
            print("🔍 Auto-detecting latest DGM output directory...")
        
        # Check if we're in the DGM directory
        if not Path("DGM_outer.py").exists():
            print("❌ Error: This script must be run from the DGM root directory")
            print("❌ Please cd to the directory containing DGM_outer.py")
            sys.exit(1)
        
        latest_output = find_latest_output_dir()
        if not latest_output:
            print("❌ Error: No DGM output directories found in output_dgm/")
            print("❌ Make sure you have run DGM_outer.py first")
            sys.exit(1)
        
        dgm_path = str(latest_output)
        if not args.quiet:
            print(f"✅ Found latest output directory: {dgm_path}")
    
    # Initialize cleanup
    cleanup = DGMPostRunCleanup(dgm_path, verbose=not args.quiet)
    
    # Run cleanup
    try:
        results = cleanup.run_full_cleanup(
            cleanup_docker=not args.no_docker,
            cleanup_images=not args.no_images,
            aggressive_images=args.aggressive_images,
            cleanup_files=not args.no_files
        )
        
        if not args.quiet:
            print("\n🎉 Cleanup completed successfully!")
            print(f"📊 Summary: {results['summary_results'].get('total_attempts', 0)} attempts, "
                  f"{results['docker_stats']['containers_removed']} containers removed, "
                  f"{results['docker_stats']['images_removed']} images removed")
        
    except KeyboardInterrupt:
        print("\n⚠️  Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()