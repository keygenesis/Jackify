"""
Example usage of ProgressParser

This file demonstrates how to use the progress parser to extract
structured information from jackify-engine output.

R&D NOTE: This is experimental code for investigation purposes.
"""

from jackify.backend.handlers.progress_parser import ProgressStateManager


def example_usage():
    """Example of how to use the progress parser."""
    
    # Create state manager
    state_manager = ProgressStateManager()
    
    # Simulate processing lines from jackify-engine output
    sample_lines = [
        "[00:00:00] === Installing files ===",
        "[00:00:05] [12/14] Installing files (1.1GB/56.3GB)",
        "[00:00:10] Installing: Enderal Remastered Armory.7z (42%)",
        "[00:00:15] Extracting: Mandragora Sprouts.7z (96%)",
        "[00:00:20] Downloading at 45.2MB/s",
        "[00:00:25] Extracting at 267.3MB/s",
        "[00:00:30] Progress: 85%",
    ]
    
    print("Processing sample output lines...\n")
    
    for line in sample_lines:
        updated = state_manager.process_line(line)
        if updated:
            state = state_manager.get_state()
            print(f"Line: {line}")
            print(f"  Phase: {state.phase.value} - {state.phase_name}")
            print(f"  Progress: {state.overall_percent:.1f}%")
            print(f"  Step: {state.phase_progress_text}")
            print(f"  Data: {state.data_progress_text}")
            print(f"  Active Files: {len(state.active_files)}")
            for file_prog in state.active_files:
                print(f"    - {file_prog.filename}: {file_prog.percent:.1f}%")
            print(f"  Speeds: {state.speeds}")
            print(f"  Display: {state.display_text}")
            print()


if __name__ == "__main__":
    example_usage()

