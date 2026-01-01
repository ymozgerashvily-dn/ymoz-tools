#!/usr/bin/env python3
"""
WebBorrow - Web interface for pyborrow.py

A Flask web application that wraps the pyborrow.py script,
displaying machines in a web interface with borrow/free buttons.

Usage:
    python app.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Path to pyborrow.py
PYBORROW_PATH = Path.home() / 'dp-tools' / 'pyborrow.py'


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


def run_pyborrow(args: list = None) -> tuple[str, str, int]:
    """
    Run pyborrow.py with given arguments.
    Returns (stdout, stderr, return_code)
    """
    cmd = [sys.executable, str(PYBORROW_PATH)]
    if args:
        cmd.extend(args)
    
    # Add -q flag for quiet mode when borrowing/freeing
    if args and ('-b' in args or '-f' in args or '--borrow' in args or '--free' in args):
        cmd.append('-q')
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes timeout for fetching
            cwd=str(PYBORROW_PATH.parent)
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1


def parse_machine_table(output: str) -> list:
    """
    Parse the pyborrow.py output to extract machine information.
    Returns a list of machine dictionaries.
    """
    machines = []
    
    # Clean the output
    clean_output = strip_ansi(output)
    lines = clean_output.split('\n')
    
    current_section = None  # 'standalone', 'cluster_X', or None
    current_cluster = None
    is_cluster_table = False
    
    for line in lines:
        # Detect section headers
        if 'Stand alone' in line:
            current_section = 'standalone'
            is_cluster_table = False
            current_cluster = None
            continue
        elif 'Cluster' in line and '─' not in line:
            match = re.search(r'Cluster\s+(\d+)', line)
            if match:
                current_cluster = match.group(1)
                current_section = f'cluster_{current_cluster}'
                is_cluster_table = True
            continue
        elif 'DP IXIAs' in line:
            current_section = 'ixia'
            continue
        elif 'Total' in line and 'Free' in line and 'Taken' in line:
            # Summary table - skip
            current_section = 'summary'
            continue
        
        # Skip if not in a valid section
        if current_section not in ['standalone'] and not current_section or current_section.startswith('cluster_') == False:
            if current_section != 'standalone':
                if not (current_section and current_section.startswith('cluster_')):
                    continue
        
        # Skip non-data lines
        if '│' not in line:
            continue
        
        # Skip header/separator lines
        if '─' in line or '┌' in line or '└' in line or '├' in line or '═' in line:
            continue
        
        # Skip lines that are just table headers
        if 'wbox_name' in line or 'vendor' in line and 'type' in line and 'revision' in line:
            continue
        
        # Parse table row - split by │
        parts = [p.strip() for p in line.split('│')]
        parts = [p for p in parts if p != '']  # Remove empty parts from edges
        
        if len(parts) < 6:
            continue
        
        machine = None
        
        # Cluster table has nce_id as first column (11 columns total)
        if is_cluster_table and len(parts) >= 10:
            # nce_id, vendor, type, revision, wbox_name, baseos_version, status, borrow_uptime, git_branch, last_connection, comment
            machine = {
                'nce_id': parts[0] if len(parts) > 0 else '',
                'vendor': parts[1] if len(parts) > 1 else '',
                'type': parts[2] if len(parts) > 2 else '',
                'revision': parts[3] if len(parts) > 3 else '',
                'name': parts[4] if len(parts) > 4 else '',
                'baseos_version': parts[5] if len(parts) > 5 else '',
                'status': parts[6] if len(parts) > 6 else '',
                'borrow_uptime': parts[7] if len(parts) > 7 else '',
                'git_branch': parts[8] if len(parts) > 8 else '',
                'last_connection': parts[9] if len(parts) > 9 else '',
                'comment': parts[10] if len(parts) > 10 else '',
                'cluster': current_cluster
            }
        # Standalone table (10 columns)
        elif not is_cluster_table and len(parts) >= 6:
            # vendor, type, revision, wbox_name, baseos_version, status, borrow_uptime, git_branch, last_connection, comment
            machine = {
                'vendor': parts[0] if len(parts) > 0 else '',
                'type': parts[1] if len(parts) > 1 else '',
                'revision': parts[2] if len(parts) > 2 else '',
                'name': parts[3] if len(parts) > 3 else '',
                'baseos_version': parts[4] if len(parts) > 4 else '',
                'status': parts[5] if len(parts) > 5 else '',
                'borrow_uptime': parts[6] if len(parts) > 6 else '',
                'git_branch': parts[7] if len(parts) > 7 else '',
                'last_connection': parts[8] if len(parts) > 8 else '',
                'comment': parts[9] if len(parts) > 9 else '',
                'cluster': None
            }
        
        if not machine or not machine.get('name'):
            continue
        
        # Skip if this looks like a header row
        if machine['name'] == 'wbox_name':
            continue
        
        # Skip continuation rows (empty name but has content in other fields)
        if not machine['name'] and not machine.get('vendor'):
            continue
        
        # Determine machine state from status
        status_lower = machine['status'].lower()
        if 'available' in status_lower:
            machine['state'] = 'available'
            machine['borrower'] = None
        elif 'no ping' in status_lower:
            machine['state'] = 'offline'
            machine['borrower'] = None
        elif 'no ssh' in status_lower:
            machine['state'] = 'no_ssh'
            machine['borrower'] = None
        elif 'no cheetah' in status_lower:
            machine['state'] = 'no_cheetah'
            machine['borrower'] = None
        elif 'deploy' in status_lower and '(' not in status_lower:
            machine['state'] = 'deployed'
            machine['borrower'] = None
        else:
            # Status contains borrower name
            machine['state'] = 'borrowed'
            # Extract borrower name (remove deploy indicator if present)
            borrower = machine['status'].replace('(deploy)', '').strip()
            machine['borrower'] = borrower if borrower else machine['status']
        
        machines.append(machine)
    
    return machines


def parse_summary(output: str) -> dict:
    """Parse the summary table from output."""
    clean_output = strip_ansi(output)
    
    summary = {
        'total': 0,
        'free': 0,
        'taken': 0,
        'taken_not_used': 0
    }
    
    # Look for summary table with double-line borders (╔ ╗ ╚ ╝)
    lines = clean_output.split('\n')
    for i, line in enumerate(lines):
        if '║' in line and '═' not in line:
            parts = [p.strip() for p in line.split('║')]
            parts = [p for p in parts if p]
            
            # Summary table has 4 numeric values
            if len(parts) == 4:
                try:
                    vals = [int(p) for p in parts]
                    if all(v >= 0 for v in vals) and vals[0] >= vals[1]:  # Total >= Free
                        summary = {
                            'total': vals[0],
                            'free': vals[1],
                            'taken': vals[2],
                            'taken_not_used': vals[3]
                        }
                        break
                except ValueError:
                    continue
    
    return summary


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/machines')
def get_machines():
    """Get list of all machines."""
    stdout, stderr, code = run_pyborrow()
    
    if code != 0 and not stdout:
        return jsonify({
            'error': f'Failed to fetch machines: {stderr}',
            'machines': [],
            'summary': {}
        }), 500
    
    machines = parse_machine_table(stdout)
    summary = parse_summary(stdout)
    
    return jsonify({
        'machines': machines,
        'summary': summary,
        'count': len(machines)
    })


@app.route('/api/borrow/<machine_name>', methods=['POST'])
def borrow_machine(machine_name):
    """Borrow a machine."""
    stdout, stderr, code = run_pyborrow(['-b', machine_name])
    
    clean_stdout = strip_ansi(stdout)
    clean_stderr = strip_ansi(stderr)
    
    if code == 0 or 'borrowed' in clean_stdout.lower():
        return jsonify({
            'success': True,
            'message': f'Successfully borrowed {machine_name}',
            'output': clean_stdout
        })
    else:
        return jsonify({
            'success': False,
            'message': f'Failed to borrow {machine_name}',
            'output': clean_stdout,
            'error': clean_stderr
        }), 400


@app.route('/api/free/<machine_name>', methods=['POST'])
def free_machine(machine_name):
    """Free a machine."""
    stdout, stderr, code = run_pyborrow(['-f', machine_name])
    
    clean_stdout = strip_ansi(stdout)
    clean_stderr = strip_ansi(stderr)
    
    if code == 0 or 'freed' in clean_stdout.lower():
        return jsonify({
            'success': True,
            'message': f'Successfully freed {machine_name}',
            'output': clean_stdout
        })
    else:
        return jsonify({
            'success': False,
            'message': f'Failed to free {machine_name}',
            'output': clean_stdout,
            'error': clean_stderr
        }), 400


@app.route('/api/machine/<machine_name>')
def get_machine_details(machine_name):
    """Get detailed info about a specific machine."""
    stdout, stderr, code = run_pyborrow([machine_name])
    
    clean_stdout = strip_ansi(stdout)
    
    return jsonify({
        'name': machine_name,
        'details': clean_stdout,
        'success': code == 0
    })


if __name__ == '__main__':
    if not PYBORROW_PATH.exists():
        print(f"❌ Error: pyborrow.py not found at {PYBORROW_PATH}")
        print("Please ensure the dp-tools repository exists at ~/dp-tools")
        sys.exit(1)
    
    print(f"🌐 WebBorrow - Web interface for pyborrow.py")
    print(f"📁 Using pyborrow.py at: {PYBORROW_PATH}")
    print()
    
    app.run(debug=True, port=80, host='0.0.0.0')
