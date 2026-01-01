#!/usr/bin/env python3
"""
Machine Cleanup Script 🧹

Cleans up a remote machine and its nested remote machine:
- Runs git clean in /home/dn/cheetah
- Removes all Docker images
- Reports disk space before/after

Usage:
    python machine_clean.py <hostname>

Example:
    python machine_clean.py dev-server-01
"""

import argparse
import sys
import os

try:
    import paramiko
except ImportError:
    print("❌ Error: paramiko is required. Install with: pip install paramiko")
    sys.exit(1)


# Configuration
SSH_PASSWORD = "drivenets"
SSH_USERNAME = "dn"  # Default username, can be overridden
SSH_PORT = 2222  # Port for main machine
SSH_PORT_NESTED = 22  # Port for nested machine (standard SSH)
CHEETAH_PATH = "/home/dn/cheetah"


class MachineCleanup:
    """Handles cleanup operations on remote machines."""
    
    def __init__(self, hostname: str, password: str, username: str = "dn", verbose: bool = False):
        self.hostname = hostname
        self.password = password
        self.username = username
        self.verbose = verbose
        self.client = None
        self.disk_before = None
        self.disk_after = None
        
    def log(self, emoji: str, message: str, indent: int = 0):
        """Print a formatted log message."""
        prefix = "  " * indent
        print(f"{prefix}{emoji} {message}")
    
    def log_verbose(self, message: str, indent: int = 0):
        """Print a verbose log message (only in verbose mode)."""
        if self.verbose:
            prefix = "  " * indent
            print(f"{prefix}🔍 [VERBOSE] {message}")
    
    def log_command(self, command: str, indent: int = 0):
        """Print the command being executed (only in verbose mode)."""
        if self.verbose:
            prefix = "  " * indent
            # Mask password in command for display
            display_cmd = command.replace(self.password, '****')
            print(f"{prefix}⚡ [CMD] {display_cmd}")
    
    def log_output(self, stdout: str, stderr: str, exit_code: int, indent: int = 0):
        """Print command output details (only in verbose mode)."""
        if self.verbose:
            prefix = "  " * indent
            print(f"{prefix}📊 [EXIT CODE] {exit_code}")
            if stdout:
                print(f"{prefix}📤 [STDOUT]")
                for line in stdout.split('\n'):
                    # Mask password in output
                    line = line.replace(self.password, '****')
                    print(f"{prefix}   {line}")
            if stderr:
                print(f"{prefix}📥 [STDERR]")
                for line in stderr.split('\n'):
                    line = line.replace(self.password, '****')
                    print(f"{prefix}   {line}")
            print(f"{prefix}{'─' * 50}")
    
    def log_section(self, title: str):
        """Print a section header."""
        print()
        print("=" * 60)
        print(f"🔷 {title}")
        print("=" * 60)
    
    def connect(self) -> bool:
        """Establish SSH connection to the machine."""
        self.log("🔌", f"Connecting to {self.username}@{self.hostname}...")
        self.log_verbose(f"SSH Port: {SSH_PORT}", indent=1)
        self.log_verbose(f"Timeout: 30 seconds", indent=1)
        
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.log_verbose("SSH client initialized, host key policy set to AutoAdd", indent=1)
        
        try:
            self.log_verbose(f"Initiating connection to {self.hostname}:{SSH_PORT}...", indent=1)
            self.client.connect(
                self.hostname,
                port=SSH_PORT,
                username=self.username,
                password=self.password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            self.log("✅", f"Connected to {self.hostname}", indent=1)
            self.log_verbose(f"Connection established successfully", indent=1)
            return True
        except paramiko.AuthenticationException as e:
            self.log("❌", f"Authentication failed for {self.hostname}", indent=1)
            self.log_verbose(f"Auth error details: {e}", indent=1)
            return False
        except paramiko.SSHException as e:
            self.log("❌", f"SSH error: {e}", indent=1)
            self.log_verbose(f"SSH exception type: {type(e).__name__}", indent=1)
            return False
        except Exception as e:
            self.log("❌", f"Connection failed: {e}", indent=1)
            self.log_verbose(f"Exception type: {type(e).__name__}", indent=1)
            return False
    
    def disconnect(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()
            self.log("🔌", f"Disconnected from {self.hostname}")
    
    def run_command(self, command: str, use_sudo: bool = False, show_output: bool = True) -> tuple[int, str, str]:
        """Run a command on the remote machine."""
        original_command = command
        if use_sudo:
            command = f"echo '{self.password}' | sudo -S {command}"
        
        # Log the command in verbose mode
        self.log_command(command, indent=2)
        
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
        
        exit_code = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode('utf-8', errors='ignore').strip()
        stderr_text = stderr.read().decode('utf-8', errors='ignore').strip()
        
        # Store raw output for verbose logging before filtering
        raw_stdout = stdout_text
        raw_stderr = stderr_text
        
        # Filter out sudo password prompt from output
        if use_sudo and stdout_text:
            lines = stdout_text.split('\n')
            stdout_text = '\n'.join(line for line in lines if '[sudo]' not in line and self.password not in line)
        
        # Verbose mode: show full output
        if self.verbose:
            self.log_output(raw_stdout, raw_stderr, exit_code, indent=2)
        elif show_output and stdout_text:
            # Normal mode: truncated output
            for line in stdout_text.split('\n')[:20]:
                self.log("📝", line, indent=2)
            if len(stdout_text.split('\n')) > 20:
                self.log("📝", "... (output truncated)", indent=2)
        
        return exit_code, stdout_text, stderr_text
    
    def get_disk_usage(self) -> list:
        """Get disk usage information for all partitions."""
        # Get all partitions, excluding tmpfs, devtmpfs, and other virtual filesystems
        _, output, _ = self.run_command(
            "df -h -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null || df -h",
            show_output=False
        )
        
        partitions = []
        lines = output.strip().split('\n')
        
        for line in lines[1:]:  # Skip header line
            parts = line.split()
            if len(parts) >= 6:
                partitions.append({
                    'filesystem': parts[0],
                    'total': parts[1],
                    'used': parts[2],
                    'available': parts[3],
                    'percent': parts[4],
                    'mountpoint': parts[5]
                })
        
        return partitions if partitions else [{'filesystem': '?', 'total': '?', 'used': '?', 'available': '?', 'percent': '?', 'mountpoint': '?'}]
    
    def display_disk_usage(self, partitions: list, label: str, indent: int = 1):
        """Display disk usage for all partitions."""
        self.log("💾", f"{label}:", indent=indent)
        for p in partitions:
            self.log("📊", f"{p['mountpoint']}: {p['used']} used / {p['total']} total ({p['percent']}) - {p['filesystem']}", indent=indent+1)
    
    def _parse_df_output(self, output: str) -> list:
        """Parse df -h output into a list of partition dictionaries."""
        partitions = []
        lines = output.strip().split('\n')
        
        for line in lines:
            # Skip header line
            if line.startswith('Filesystem') or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 6:
                partitions.append({
                    'filesystem': parts[0],
                    'total': parts[1],
                    'used': parts[2],
                    'available': parts[3],
                    'percent': parts[4],
                    'mountpoint': parts[5]
                })
        
        return partitions if partitions else [{'filesystem': '?', 'total': '?', 'used': '?', 'available': '?', 'percent': '?', 'mountpoint': '?'}]
    
    def get_docker_space(self) -> str:
        """Get Docker disk usage."""
        _, output, _ = self.run_command("docker system df 2>/dev/null | head -5", show_output=False)
        return output if output else "Docker not available"
    
    def git_clean(self) -> bool:
        """Run git clean in the cheetah directory."""
        self.log("🧹", f"Running git clean in {CHEETAH_PATH}...")
        self.log_verbose(f"Target directory: {CHEETAH_PATH}", indent=1)
        self.log_verbose("Command: git clean -xdf (remove untracked files, directories, and ignored files)", indent=1)
        
        # Check if directory exists
        self.log_verbose("Checking if directory exists...", indent=1)
        exit_code, _, _ = self.run_command(f"test -d {CHEETAH_PATH}", show_output=False)
        if exit_code != 0:
            self.log("⚠️", f"Directory {CHEETAH_PATH} does not exist, skipping git clean", indent=1)
            return True
        
        self.log_verbose("Directory exists, proceeding with git clean", indent=1)
        
        # Run git clean (use bash -c to handle cd with sudo)
        exit_code, output, stderr = self.run_command(
            f"bash -c 'cd {CHEETAH_PATH} && git clean -xdf'",
            use_sudo=True
        )
        
        if exit_code == 0:
            self.log("✅", "Git clean completed successfully", indent=1)
            self.log_verbose(f"Files removed: {len(output.splitlines()) if output else 0} items", indent=1)
            return True
        else:
            self.log("⚠️", f"Git clean had issues: {stderr}", indent=1)
            self.log_verbose(f"Exit code: {exit_code}", indent=1)
            return False
    
    def docker_cleanup(self) -> bool:
        """Remove all Docker images and clean up Docker."""
        self.log("🐳", "Cleaning up Docker...")
        
        # Get Docker info before cleanup (verbose only)
        if self.verbose:
            self.log_verbose("Gathering Docker state before cleanup...", indent=1)
            self.run_command("docker ps -a 2>/dev/null || true", show_output=False)
            self.run_command("docker images 2>/dev/null || true", show_output=False)
            self.run_command("docker system df 2>/dev/null || true", show_output=False)
        
        # Stop all running containers
        self.log("🛑", "Stopping all containers...", indent=1)
        self.log_verbose("Command: docker stop $(docker ps -aq)", indent=2)
        self.run_command("docker stop $(docker ps -aq) 2>/dev/null || true", show_output=False)
        
        # Remove all containers
        self.log("🗑️", "Removing all containers...", indent=1)
        self.log_verbose("Command: docker rm -f $(docker ps -aq)", indent=2)
        exit_code, output, _ = self.run_command("docker rm -f $(docker ps -aq) 2>/dev/null || true", show_output=False)
        
        # Remove all images
        self.log("🖼️", "Removing all Docker images...", indent=1)
        self.log_verbose("Command: docker rmi -f $(docker images -aq)", indent=2)
        exit_code, output, _ = self.run_command("docker rmi -f $(docker images -aq) 2>/dev/null || true")
        
        # Docker system prune
        self.log("🧽", "Running Docker system prune...", indent=1)
        self.log_verbose("Command: docker system prune -af --volumes (remove all unused data)", indent=2)
        exit_code, output, _ = self.run_command("docker system prune -af --volumes 2>/dev/null || true", show_output=False)
        
        # Get Docker info after cleanup (verbose only)
        if self.verbose:
            self.log_verbose("Docker state after cleanup:", indent=1)
            self.run_command("docker system df 2>/dev/null || true", show_output=False)
        
        self.log("✅", "Docker cleanup completed", indent=1)
        return True
    
    def get_remote_machine_var(self) -> str:
        """Get the $REMOTE_MACHINE environment variable."""
        self.log_verbose("Checking $REMOTE_MACHINE...", indent=1)
        
        # Try multiple methods to find the variable
        methods = [
            # Method 1: Login shell
            ("login shell", "bash -l -c 'echo $REMOTE_MACHINE'"),
            # Method 2: Interactive login shell
            ("interactive login shell", "bash -li -c 'echo $REMOTE_MACHINE' 2>/dev/null"),
            # Method 3: Source .bashrc directly
            ("source .bashrc", "bash -c 'source ~/.bashrc 2>/dev/null; echo $REMOTE_MACHINE'"),
            # Method 4: Source .profile
            ("source .profile", "bash -c 'source ~/.profile 2>/dev/null; echo $REMOTE_MACHINE'"),
            # Method 5: Check /etc/environment
            ("grep /etc/environment", "grep -oP 'REMOTE_MACHINE=\\K.*' /etc/environment 2>/dev/null"),
            # Method 6: Check common profile.d scripts
            ("source profile.d", "bash -c 'for f in /etc/profile.d/*.sh; do source $f 2>/dev/null; done; echo $REMOTE_MACHINE'"),
        ]
        
        for method_name, cmd in methods:
            self.log_verbose(f"Trying {method_name}...", indent=2)
            _, output, _ = self.run_command(cmd, show_output=False)
            result = output.strip() if output.strip() else None
            if result:
                self.log_verbose(f"Found via {method_name}: {result}", indent=2)
                return result
        
        # Last resort: search for it in config files
        self.log_verbose("Searching config files for REMOTE_MACHINE...", indent=2)
        _, output, _ = self.run_command(
            "grep -h 'REMOTE_MACHINE=' ~/.bashrc ~/.profile ~/.bash_profile /etc/environment /etc/profile 2>/dev/null | head -1",
            show_output=False
        )
        if output and 'REMOTE_MACHINE=' in output:
            # Extract the value
            import re
            match = re.search(r'REMOTE_MACHINE=(["\']?)([^"\'#\s]+)\1', output)
            if match:
                result = match.group(2)
                self.log_verbose(f"Found in config file: {result}", indent=2)
                return result
        
        self.log_verbose("$REMOTE_MACHINE not found in any location", indent=2)
        return None
    
    def cleanup_nested_machine(self, remote_machine: str) -> dict:
        """SSH into nested machine and clean Docker there."""
        self.log_section(f"Cleaning Nested Machine: {remote_machine}")
        
        result = {
            'hostname': remote_machine,
            'disk_before': None,
            'disk_after': None,
            'success': False
        }
        
        # Run commands through nested SSH
        self.log("🔌", f"Connecting to nested machine {remote_machine}...")
        self.log_verbose(f"Using nested SSH via sshpass", indent=1)
        self.log_verbose(f"Target: {self.username}@{remote_machine}:{SSH_PORT_NESTED}", indent=1)
        
        # Get disk usage before
        self.log_verbose("Fetching disk usage before cleanup...", indent=1)
        _, output, _ = self.run_command(
            f"sshpass -p '{self.password}' ssh -p {SSH_PORT_NESTED} -o StrictHostKeyChecking=no {self.username}@{remote_machine} 'df -h -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null || df -h'",
            show_output=False
        )
        if output:
            result['disk_before'] = self._parse_df_output(output)
            self.display_disk_usage(result['disk_before'], "Disk space BEFORE cleanup")
        
        # Stop and remove containers
        self.log("🐳", "Cleaning Docker on nested machine...", indent=1)
        
        docker_commands = [
            ("Stopping containers", "docker stop $(docker ps -aq) 2>/dev/null || true"),
            ("Removing containers", "docker rm -f $(docker ps -aq) 2>/dev/null || true"),
            ("Removing images", "docker rmi -f $(docker images -aq) 2>/dev/null || true"),
            ("System prune", "docker system prune -af --volumes 2>/dev/null || true")
        ]
        
        for desc, cmd in docker_commands:
            self.log_verbose(f"{desc}: {cmd}", indent=2)
            self.run_command(
                f"sshpass -p '{self.password}' ssh -p {SSH_PORT_NESTED} -o StrictHostKeyChecking=no {self.username}@{remote_machine} '{cmd}'",
                show_output=False
            )
        
        self.log("✅", "Docker cleanup completed on nested machine", indent=1)
        
        # Get disk usage after
        self.log_verbose("Fetching disk usage after cleanup...", indent=1)
        _, output, _ = self.run_command(
            f"sshpass -p '{self.password}' ssh -p {SSH_PORT_NESTED} -o StrictHostKeyChecking=no {self.username}@{remote_machine} 'df -h -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null || df -h'",
            show_output=False
        )
        if output:
            result['disk_after'] = self._parse_df_output(output)
            self.display_disk_usage(result['disk_after'], "Disk space AFTER cleanup")
        
        result['success'] = True
        self.log_verbose("Nested machine cleanup completed successfully", indent=1)
        return result
    
    def run_full_cleanup(self) -> dict:
        """Run the complete cleanup process."""
        results = {
            'main_machine': {
                'hostname': self.hostname,
                'disk_before': None,
                'disk_after': None,
                'success': False
            },
            'nested_machine': None
        }
        
        # Connect to main machine
        self.log_section(f"Cleaning Main Machine: {self.hostname}")
        
        if not self.connect():
            return results
        
        try:
            # Get disk usage before
            results['main_machine']['disk_before'] = self.get_disk_usage()
            self.display_disk_usage(results['main_machine']['disk_before'], "Disk space BEFORE cleanup")
            
            # Run git clean
            self.git_clean()
            
            # Docker cleanup
            self.docker_cleanup()
            
            # Get disk usage after
            results['main_machine']['disk_after'] = self.get_disk_usage()
            self.display_disk_usage(results['main_machine']['disk_after'], "Disk space AFTER cleanup")
            
            results['main_machine']['success'] = True
            
            # Check for nested machine
            remote_machine = self.get_remote_machine_var()
            if remote_machine:
                self.log("🔍", f"Found $REMOTE_MACHINE: {remote_machine}")
                results['nested_machine'] = self.cleanup_nested_machine(remote_machine)
            else:
                self.log("ℹ️", "$REMOTE_MACHINE not set, skipping nested machine cleanup")
            
        finally:
            self.disconnect()
        
        return results


def parse_size(s: str) -> float:
    """Parse a size string like '4.3G' into bytes."""
    s = s.upper().strip()
    multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return float(s[:-1]) * mult
    return float(s)


def format_size(bytes_val: float) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'K', 'M', 'G', 'T']:
        if abs(bytes_val) < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}P"


def print_partition_summary(before_list: list, after_list: list):
    """Print summary comparing before/after for all partitions."""
    # Create lookup by mountpoint
    after_by_mount = {p['mountpoint']: p for p in after_list}
    
    total_freed = 0
    
    for before in before_list:
        mount = before['mountpoint']
        after = after_by_mount.get(mount)
        
        if after:
            print(f"\n   📁 {mount} ({before['filesystem']})")
            print(f"      📥 Before:    {before['used']} used / {before['total']} total ({before['percent']})")
            print(f"      📤 After:     {after['used']} used / {after['total']} total ({after['percent']})")
            print(f"      💾 Available: {after['available']}")
            
            try:
                before_bytes = parse_size(before['used'])
                after_bytes = parse_size(after['used'])
                freed = before_bytes - after_bytes
                total_freed += freed
                
                if freed > 0:
                    print(f"      🎊 Freed:     {format_size(freed)}")
                elif freed < 0:
                    print(f"      ⚠️  Increased: {format_size(abs(freed))}")
                else:
                    print(f"      ➡️  No change")
            except:
                pass
    
    if total_freed != 0:
        print()
        if total_freed > 0:
            print(f"   🎉 TOTAL SPACE FREED: {format_size(total_freed)}")
        else:
            print(f"   ⚠️  TOTAL SPACE INCREASED: {format_size(abs(total_freed))}")


def print_summary(results: dict):
    """Print a summary of the cleanup results."""
    print()
    print("=" * 70)
    print("🎉 CLEANUP SUMMARY")
    print("=" * 70)
    
    # Main machine
    main = results['main_machine']
    print()
    print(f"📍 Main Machine: {main['hostname']}")
    print("-" * 50)
    
    if main['success'] and main['disk_before'] and main['disk_after']:
        print_partition_summary(main['disk_before'], main['disk_after'])
    else:
        print("   ❌ Cleanup failed or incomplete")
    
    # Nested machine
    if results['nested_machine']:
        nested = results['nested_machine']
        print()
        print(f"📍 Nested Machine: {nested['hostname']}")
        print("-" * 50)
        
        if nested['success'] and nested['disk_before'] and nested['disk_after']:
            print_partition_summary(nested['disk_before'], nested['disk_after'])
        else:
            print("   ❌ Cleanup failed or incomplete")
    else:
        print()
        print("📍 Nested Machine: Not configured (no $REMOTE_MACHINE)")
    
    print()
    print("=" * 70)
    print("✨ Cleanup complete! Have a great day! ✨")
    print("=" * 70)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='🧹 Machine Cleanup Script - Clean up remote machines',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s dev-server-01
    %(prog)s 192.168.1.100
    %(prog)s myhost.example.com -u admin
        """
    )
    parser.add_argument(
        'hostname',
        help='Remote machine hostname or IP address'
    )
    parser.add_argument(
        '-u', '--username',
        default='dn',
        help='SSH username (default: dn)'
    )
    parser.add_argument(
        '-p', '--password',
        default=SSH_PASSWORD,
        help='SSH password (default: drivenets)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose mode with maximum technical details'
    )
    
    args = parser.parse_args()
    
    print()
    print("🧹" + "=" * 58)
    print("   MACHINE CLEANUP TOOL")
    print("   Cleaning up disk space on remote machines")
    print("=" * 60)
    
    if args.verbose:
        print("🔍 VERBOSE MODE ENABLED - Showing all technical details")
        print()
    
    cleaner = MachineCleanup(
        hostname=args.hostname,
        password=args.password,
        username=args.username,
        verbose=args.verbose
    )
    
    results = cleaner.run_full_cleanup()
    print_summary(results)
    
    # Exit with appropriate code
    if results['main_machine']['success']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()

