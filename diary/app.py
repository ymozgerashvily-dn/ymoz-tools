#!/usr/bin/env python3
from __future__ import annotations
"""
Diary Web App - Git-based persistent diary

A Flask web application that manages diary entries stored in a git repository.
Entries are organized by year/month/day folders and synced with a remote repo.

Usage:
    python app.py

Configuration:
    Set DIARY_REPO_PATH environment variable to point to your diary git repo.
    Default: ~/.diary
"""

import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
import uuid

app = Flask(__name__)

# Configuration
DIARY_REPO_PATH = Path(os.environ.get('DIARY_REPO_PATH', Path.home() / '.diary'))
# Remote can be overridden via env; defaults to requested GitHub repo
DIARY_REMOTE_URL = os.environ.get('DIARY_REMOTE_URL', 'git@github.com:ymozgerashvily-dn/diary.git')
SYNC_INTERVAL = 15  # seconds

# Global sync state
sync_state = {
    'last_sync': None,
    'last_error': None,
    'syncing': False
}


def ensure_remote_configured():
    """Ensure the git remote 'origin' points to the configured remote URL."""
    if not DIARY_REMOTE_URL:
        return
    
    # Check current remote; add or update as needed
    success, output = run_git_command(['remote', 'get-url', 'origin'])
    if success:
        current_url = output.strip()
        if current_url != DIARY_REMOTE_URL:
            run_git_command(['remote', 'set-url', 'origin', DIARY_REMOTE_URL])
    else:
        run_git_command(['remote', 'add', 'origin', DIARY_REMOTE_URL])


def ensure_repo_exists():
    """Ensure the diary repository exists, is a git repo, and has the remote set."""
    repo_created = False
    
    if not DIARY_REPO_PATH.exists():
        DIARY_REPO_PATH.mkdir(parents=True)
        repo_created = True
    
    if not (DIARY_REPO_PATH / '.git').exists():
        run_git_command(['init'])
        repo_created = True
    
    if repo_created:
        # Create initial README if missing
        readme_path = DIARY_REPO_PATH / 'README.md'
        if not readme_path.exists():
            readme_path.write_text('# My Diary\n\nPersonal diary entries managed by the Diary Web App.\n')
            run_git_command(['add', 'README.md'])
            run_git_command(['commit', '-m', 'Initial commit'])
        print(f"📓 Initialized diary repository at {DIARY_REPO_PATH}")
    
    ensure_remote_configured()
    return True


def run_git_command(args: list, capture_output=True) -> tuple[bool, str]:
    """Run a git command in the diary repository."""
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=str(DIARY_REPO_PATH),
            capture_output=capture_output,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def sync_with_remote():
    """Sync local repo with remote (pull then push)."""
    global sync_state
    
    if sync_state['syncing']:
        return False, "Sync already in progress"
    
    sync_state['syncing'] = True
    
    try:
        # Ensure remote is configured before attempting sync
        ensure_remote_configured()
        
        # Check if remote exists
        success, output = run_git_command(['remote', '-v'])
        if not success or 'origin' not in output:
            sync_state['syncing'] = False
            return True, "No remote configured - local only mode"
        
        # Pull changes
        success, output = run_git_command(['pull', '--rebase', 'origin', 'main'])
        if not success:
            # Try master branch
            success, output = run_git_command(['pull', '--rebase', 'origin', 'master'])
        
        if not success and 'Could not read from remote' not in output:
            sync_state['last_error'] = f"Pull failed: {output}"
        
        # Push changes
        success, output = run_git_command(['push', 'origin', 'HEAD'])
        if not success and 'Could not read from remote' not in output:
            sync_state['last_error'] = f"Push failed: {output}"
        
        sync_state['last_sync'] = datetime.now().isoformat()
        sync_state['last_error'] = None
        return True, "Sync complete"
        
    except Exception as e:
        sync_state['last_error'] = str(e)
        return False, str(e)
    finally:
        sync_state['syncing'] = False


def get_day_folder_name(date: datetime) -> str:
    """Get the day folder name in format: DD-DayName (e.g., 04-Mon)."""
    return date.strftime('%d-%a')


def get_entry_path(date: datetime, entry_id: str = None) -> Path:
    """Get the path for a diary entry."""
    year = date.strftime('%Y')
    month = date.strftime('%m')
    day = get_day_folder_name(date)
    
    folder = DIARY_REPO_PATH / year / month / day
    
    if entry_id:
        return folder / f"{entry_id}.md"
    return folder


def create_entry(content: str, date: datetime = None) -> dict:
    """Create a new diary entry."""
    if date is None:
        date = datetime.now()
    
    # Generate unique ID with timestamp
    timestamp = date.strftime('%H%M%S')
    entry_id = f"{timestamp}_{uuid.uuid4().hex[:6]}"
    
    # Create folder structure
    folder = get_entry_path(date)
    folder.mkdir(parents=True, exist_ok=True)
    
    # Create entry file
    entry_path = folder / f"{entry_id}.md"
    
    # Format entry with metadata
    entry_content = f"""---
date: {date.strftime('%Y-%m-%d %H:%M:%S')}
---

{content}
"""
    
    entry_path.write_text(entry_content)
    
    # Git add and commit
    relative_path = entry_path.relative_to(DIARY_REPO_PATH)
    run_git_command(['add', str(relative_path)])
    commit_msg = f"Add entry: {date.strftime('%Y-%m-%d %H:%M')}"
    run_git_command(['commit', '-m', commit_msg])
    
    return {
        'id': entry_id,
        'date': date.isoformat(),
        'path': str(relative_path),
        'content': content
    }


def delete_entry(year: str, month: str, day: str, entry_id: str) -> bool:
    """Delete a diary entry."""
    entry_path = DIARY_REPO_PATH / year / month / day / f"{entry_id}.md"
    
    if not entry_path.exists():
        return False
    
    entry_path.unlink()
    
    # Git add and commit
    relative_path = entry_path.relative_to(DIARY_REPO_PATH)
    run_git_command(['add', str(relative_path)])
    commit_msg = f"Delete entry: {year}-{month}-{day}/{entry_id}"
    run_git_command(['commit', '-m', commit_msg])
    
    return True


def get_all_entries() -> list:
    """Get all diary entries organized by date."""
    entries = []
    
    if not DIARY_REPO_PATH.exists():
        return entries
    
    # Walk through year/month/day structure
    for year_dir in sorted(DIARY_REPO_PATH.iterdir(), reverse=True):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        
        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            
            for day_dir in sorted(month_dir.iterdir(), reverse=True):
                if not day_dir.is_dir() or '-' not in day_dir.name:
                    continue
                
                day_entries = []
                for entry_file in sorted(day_dir.glob('*.md'), reverse=True):
                    content = entry_file.read_text()
                    
                    # Parse metadata
                    entry_date = None
                    entry_content = content
                    
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            metadata = parts[1].strip()
                            entry_content = parts[2].strip()
                            
                            for line in metadata.split('\n'):
                                if line.startswith('date:'):
                                    entry_date = line.replace('date:', '').strip()
                    
                    day_entries.append({
                        'id': entry_file.stem,
                        'date': entry_date,
                        'content': entry_content,
                        'year': year_dir.name,
                        'month': month_dir.name,
                        'day': day_dir.name
                    })
                
                if day_entries:
                    entries.append({
                        'year': year_dir.name,
                        'month': month_dir.name,
                        'day': day_dir.name,
                        'entries': day_entries
                    })
    
    return entries


# --- Todo functions ---

TODOS_FILE = 'todos.json'


def _todos_path() -> Path:
    return DIARY_REPO_PATH / TODOS_FILE


def load_todos() -> list:
    """Load todos from the JSON file."""
    path = _todos_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_todos(todos: list):
    """Save todos to the JSON file and commit."""
    path = _todos_path()
    path.write_text(json.dumps(todos, indent=2) + '\n')
    run_git_command(['add', TODOS_FILE])
    run_git_command(['commit', '-m', 'Update todos'])


def create_todo(text: str) -> dict:
    """Create a new todo item."""
    todos = load_todos()
    todo = {
        'id': uuid.uuid4().hex[:8],
        'text': text,
        'done': False,
        'created': datetime.now().isoformat(),
    }
    todos.append(todo)
    save_todos(todos)
    return todo


def toggle_todo(todo_id: str) -> dict | None:
    """Toggle a todo's done state. Returns the updated todo or None."""
    todos = load_todos()
    for t in todos:
        if t['id'] == todo_id:
            t['done'] = not t['done']
            save_todos(todos)
            return t
    return None


def update_todo_text(todo_id: str, text: str) -> dict | None:
    """Update a todo's text. Returns the updated todo or None."""
    todos = load_todos()
    for t in todos:
        if t['id'] == todo_id:
            t['text'] = text
            save_todos(todos)
            return t
    return None


def delete_todo(todo_id: str) -> bool:
    """Delete a todo by id."""
    todos = load_todos()
    new_todos = [t for t in todos if t['id'] != todo_id]
    if len(new_todos) == len(todos):
        return False
    save_todos(new_todos)
    return True


def background_sync():
    """Background thread for periodic sync."""
    while True:
        time.sleep(SYNC_INTERVAL)
        try:
            sync_with_remote()
        except Exception as e:
            sync_state['last_error'] = str(e)


# Routes
@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/entries')
def api_get_entries():
    """Get all diary entries."""
    entries = get_all_entries()
    return jsonify({
        'entries': entries,
        'sync_state': sync_state
    })


@app.route('/api/entries', methods=['POST'])
def api_create_entry():
    """Create a new diary entry."""
    data = request.json
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'error': 'Content is required'}), 400
    
    # Parse date if provided
    date = datetime.now()
    if data.get('date'):
        try:
            date = datetime.fromisoformat(data['date'])
        except:
            pass
    
    entry = create_entry(content, date)
    
    # Trigger sync
    threading.Thread(target=sync_with_remote, daemon=True).start()
    
    return jsonify({
        'success': True,
        'entry': entry
    })


@app.route('/api/entries/<year>/<month>/<day>/<entry_id>', methods=['DELETE'])
def api_delete_entry(year, month, day, entry_id):
    """Delete a diary entry."""
    success = delete_entry(year, month, day, entry_id)
    
    if success:
        # Trigger sync
        threading.Thread(target=sync_with_remote, daemon=True).start()
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Entry not found'}), 404


@app.route('/api/sync', methods=['POST'])
def api_sync():
    """Manually trigger sync."""
    success, message = sync_with_remote()
    return jsonify({
        'success': success,
        'message': message,
        'sync_state': sync_state
    })


@app.route('/api/status')
def api_status():
    """Get sync status."""
    return jsonify(sync_state)


# --- Todo API routes ---

@app.route('/api/todos')
def api_get_todos():
    """Get all todos."""
    return jsonify({'todos': load_todos()})


@app.route('/api/todos', methods=['POST'])
def api_create_todo():
    """Create a new todo."""
    data = request.json
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Text is required'}), 400
    todo = create_todo(text)
    threading.Thread(target=sync_with_remote, daemon=True).start()
    return jsonify({'success': True, 'todo': todo})


@app.route('/api/todos/<todo_id>/toggle', methods=['POST'])
def api_toggle_todo(todo_id):
    """Toggle a todo's done state."""
    todo = toggle_todo(todo_id)
    if todo:
        threading.Thread(target=sync_with_remote, daemon=True).start()
        return jsonify({'success': True, 'todo': todo})
    return jsonify({'error': 'Todo not found'}), 404


@app.route('/api/todos/<todo_id>', methods=['PUT'])
def api_update_todo(todo_id):
    """Update a todo's text."""
    data = request.json
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Text is required'}), 400
    todo = update_todo_text(todo_id, text)
    if todo:
        threading.Thread(target=sync_with_remote, daemon=True).start()
        return jsonify({'success': True, 'todo': todo})
    return jsonify({'error': 'Todo not found'}), 404


@app.route('/api/todos/<todo_id>', methods=['DELETE'])
def api_delete_todo(todo_id):
    """Delete a todo."""
    if delete_todo(todo_id):
        threading.Thread(target=sync_with_remote, daemon=True).start()
        return jsonify({'success': True})
    return jsonify({'error': 'Todo not found'}), 404


if __name__ == '__main__':
    print(f"📓 Diary Web App")
    print(f"📁 Repository: {DIARY_REPO_PATH}")
    print(f"🔄 Sync interval: {SYNC_INTERVAL} seconds")
    print()
    
    # Ensure repo exists
    ensure_repo_exists()
    
    # Start background sync thread
    sync_thread = threading.Thread(target=background_sync, daemon=True)
    sync_thread.start()
    print("🔄 Background sync started")
    
    # Initial sync
    threading.Thread(target=sync_with_remote, daemon=True).start()
    
    print()
    app.run(debug=True, port=5052, host='0.0.0.0')

