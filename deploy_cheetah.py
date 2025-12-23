#!/usr/bin/env python3
"""
Script to deploy cheetah scripts to a remote machine via SCP.

Usage:
    python deploy_cheetah.py <hostname>
    
Example:
    python deploy_cheetah.py my-server.example.com
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Script file extensions to copy
SCRIPT_EXTENSIONS = {'.py', '.sh', '.bash', '.pl', '.rb', '.js', '.ts'}

# Remote destination path
REMOTE_PATH = '/home/dn/cheetah'


def get_script_root() -> Path:
    """Get the root directory of this repository."""
    return Path(__file__).parent.resolve()


def get_cheetah_dir() -> Path:
    """Get the local cheetah directory path."""
    return get_script_root() / 'cheetah'


def find_script_files(directory: Path) -> list[Path]:
    """Find all script files in the given directory."""
    if not directory.exists():
        return []
    
    script_files = []
    for file_path in directory.rglob('*'):
        if file_path.is_file():
            # Check if file has a script extension
            if file_path.suffix.lower() in SCRIPT_EXTENSIONS:
                script_files.append(file_path)
            # Also check for files with shebang (executable scripts without extension)
            elif not file_path.suffix:
                try:
                    with open(file_path, 'rb') as f:
                        first_bytes = f.read(2)
                        if first_bytes == b'#!':
                            script_files.append(file_path)
                except (IOError, PermissionError):
                    pass
    
    return sorted(script_files)


def scp_files(files: list[Path], hostname: str, remote_path: str, cheetah_dir: Path) -> bool:
    """
    Copy files to remote machine using SCP.
    
    Returns True if all files were copied successfully, False otherwise.
    """
    if not files:
        print("No script files found to copy.")
        return True
    
    # First, ensure the remote directory exists
    print(f"Creating remote directory: {remote_path}")
    mkdir_cmd = ['ssh', hostname, f'mkdir -p {remote_path}']
    result = subprocess.run(mkdir_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error creating remote directory: {result.stderr}")
        return False
    
    success = True
    for file_path in files:
        # Calculate relative path to preserve directory structure
        relative_path = file_path.relative_to(cheetah_dir)
        remote_file_path = f"{remote_path}/{relative_path}"
        
        # Create remote subdirectory if needed
        if relative_path.parent != Path('.'):
            remote_subdir = f"{remote_path}/{relative_path.parent}"
            mkdir_cmd = ['ssh', hostname, f'mkdir -p {remote_subdir}']
            subprocess.run(mkdir_cmd, capture_output=True, text=True)
        
        # Copy the file
        print(f"Copying: {relative_path} -> {hostname}:{remote_file_path}")
        scp_cmd = ['scp', str(file_path), f'{hostname}:{remote_file_path}']
        result = subprocess.run(scp_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"  Error: {result.stderr.strip()}")
            success = False
        else:
            print(f"  Done")
    
    return success


def main():
    parser = argparse.ArgumentParser(
        description='Deploy cheetah scripts to a remote machine via SCP.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s my-server.example.com
    %(prog)s user@192.168.1.100
    %(prog)s my-server --dry-run
        """
    )
    parser.add_argument(
        'hostname',
        help='Remote machine hostname or user@hostname'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be copied without actually copying'
    )
    parser.add_argument(
        '--remote-path', '-r',
        default=REMOTE_PATH,
        help=f'Remote destination path (default: {REMOTE_PATH})'
    )
    
    args = parser.parse_args()
    
    cheetah_dir = get_cheetah_dir()
    
    if not cheetah_dir.exists():
        print(f"Error: Cheetah directory not found: {cheetah_dir}")
        print("Please create the 'cheetah' directory in the repository root.")
        sys.exit(1)
    
    print(f"Source directory: {cheetah_dir}")
    print(f"Remote destination: {args.hostname}:{args.remote_path}")
    print()
    
    script_files = find_script_files(cheetah_dir)
    
    if not script_files:
        print("No script files found in the cheetah directory.")
        sys.exit(0)
    
    print(f"Found {len(script_files)} script file(s):")
    for f in script_files:
        print(f"  - {f.relative_to(cheetah_dir)}")
    print()
    
    if args.dry_run:
        print("Dry run mode - no files were copied.")
        sys.exit(0)
    
    success = scp_files(script_files, args.hostname, args.remote_path, cheetah_dir)
    
    if success:
        print("\nAll files copied successfully!")
        sys.exit(0)
    else:
        print("\nSome files failed to copy.")
        sys.exit(1)


if __name__ == '__main__':
    main()

