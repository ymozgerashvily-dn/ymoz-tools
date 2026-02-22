#!/usr/bin/env python3
"""
Machine Copy Files Script 📂

Copies the local folder ~/yossi_moz_wbox_machine_content (with all its content)
to a remote machine at /home/dn/yossi_moz_content using SCP.

Usage:
    python machine_copy_files.py <hostname>

Example:
    python machine_copy_files.py dev-server-01
"""

import argparse
import sys
import os
import stat

try:
    import paramiko
except ImportError:
    print("❌ Error: paramiko is required. Install with: pip install paramiko")
    sys.exit(1)


# Configuration
SSH_PASSWORD = "drivenets"
SSH_USERNAME = "dn"
SSH_PORT = 2222
LOCAL_FOLDER = os.path.expanduser("~/yossi_moz_wbox_machine_content")
REMOTE_FOLDER = "/home/dn/yossi_moz_content"


class MachineCopyFiles:
    """Handles recursive SCP copy of a local folder to a remote machine."""

    def __init__(self, hostname: str, password: str, username: str = "dn", verbose: bool = False):
        self.hostname = hostname
        self.password = password
        self.username = username
        self.verbose = verbose
        self.client = None
        self.sftp = None
        self.files_copied = 0
        self.dirs_created = 0

    def log(self, emoji: str, message: str, indent: int = 0):
        """Print a formatted log message."""
        prefix = "  " * indent
        print(f"{prefix}{emoji} {message}")

    def log_verbose(self, message: str, indent: int = 0):
        """Print a verbose log message (only in verbose mode)."""
        if self.verbose:
            prefix = "  " * indent
            print(f"{prefix}🔍 [VERBOSE] {message}")

    def log_section(self, title: str):
        """Print a section header."""
        print()
        print("=" * 60)
        print(f"🔷 {title}")
        print("=" * 60)

    def connect(self) -> bool:
        """Establish SSH connection and open SFTP session."""
        self.log("🔌", f"Connecting to {self.username}@{self.hostname}...")
        self.log_verbose(f"SSH Port: {SSH_PORT}", indent=1)

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.client.connect(
                self.hostname,
                port=SSH_PORT,
                username=self.username,
                password=self.password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            self.sftp = self.client.open_sftp()
            self.log("✅", f"Connected to {self.hostname}", indent=1)
            return True
        except paramiko.AuthenticationException:
            self.log("❌", f"Authentication failed for {self.hostname}", indent=1)
            return False
        except paramiko.SSHException as e:
            self.log("❌", f"SSH error: {e}", indent=1)
            return False
        except Exception as e:
            self.log("❌", f"Connection failed: {e}", indent=1)
            return False

    def disconnect(self):
        """Close SFTP and SSH connections."""
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
            self.log("🔌", f"Disconnected from {self.hostname}")

    def _remote_mkdir_p(self, remote_path: str):
        """Recursively create remote directories (like mkdir -p)."""
        dirs_to_create = []
        current = remote_path

        while True:
            try:
                self.sftp.stat(current)
                break
            except FileNotFoundError:
                dirs_to_create.append(current)
                current = os.path.dirname(current)
                if current == "/" or current == "":
                    break

        for d in reversed(dirs_to_create):
            self.log_verbose(f"Creating remote directory: {d}", indent=2)
            self.sftp.mkdir(d)
            self.dirs_created += 1

    def _copy_recursive(self, local_path: str, remote_path: str):
        """Recursively copy a local directory tree to the remote machine."""
        self._remote_mkdir_p(remote_path)

        for entry in sorted(os.listdir(local_path)):
            local_entry = os.path.join(local_path, entry)
            remote_entry = remote_path + "/" + entry

            if os.path.isdir(local_entry):
                self._copy_recursive(local_entry, remote_entry)
            else:
                self.log_verbose(f"Copying: {local_entry} -> {remote_entry}", indent=2)
                self.sftp.put(local_entry, remote_entry)
                self.files_copied += 1

                if not self.verbose and self.files_copied % 50 == 0:
                    self.log("📄", f"{self.files_copied} files copied so far...", indent=2)

    def run_copy(self) -> bool:
        """Run the full copy process."""
        self.log_section(f"Copying files to {self.hostname}")

        # Validate local folder
        if not os.path.isdir(LOCAL_FOLDER):
            self.log("❌", f"Local folder not found: {LOCAL_FOLDER}")
            return False

        local_file_count = sum(len(files) for _, _, files in os.walk(LOCAL_FOLDER))
        self.log("📂", f"Local folder: {LOCAL_FOLDER}")
        self.log("📊", f"Files to copy: {local_file_count}")
        self.log("📍", f"Remote destination: {REMOTE_FOLDER}")
        print()

        if not self.connect():
            return False

        try:
            self.log("🚀", "Starting copy...")
            self._copy_recursive(LOCAL_FOLDER, REMOTE_FOLDER)
            self.log("✅", f"Copy completed: {self.files_copied} files, {self.dirs_created} directories created")
            return True
        except Exception as e:
            self.log("❌", f"Copy failed: {e}")
            self.log_verbose(f"Exception type: {type(e).__name__}", indent=1)
            return False
        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description='📂 Machine Copy Files - Copy local folder to remote machine via SCP',
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
    print("📂" + "=" * 58)
    print("   MACHINE COPY FILES TOOL")
    print(f"   {LOCAL_FOLDER} -> {REMOTE_FOLDER}")
    print("=" * 60)

    if args.verbose:
        print("🔍 VERBOSE MODE ENABLED - Showing all technical details")
        print()

    copier = MachineCopyFiles(
        hostname=args.hostname,
        password=args.password,
        username=args.username,
        verbose=args.verbose
    )

    success = copier.run_copy()

    print()
    print("=" * 60)
    if success:
        print("✨ Copy complete! Have a great day! ✨")
    else:
        print("❌ Copy failed. Check the errors above.")
    print("=" * 60)
    print()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
