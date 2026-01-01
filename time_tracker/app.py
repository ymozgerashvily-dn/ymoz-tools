#!/usr/bin/env python3
"""
Time Tracker - A simple web application to track time spent on subjects.

Usage:
    python app.py

The database is stored at ~/.time_tracker/time_tracker.db
"""

import os
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, g

app = Flask(__name__)

# Database location in home folder
DB_DIR = Path.home() / '.time_tracker'
DB_PATH = DB_DIR / 'time_tracker.db'


def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        # Ensure directory exists
        DB_DIR.mkdir(exist_ok=True)
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database with required tables."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT DEFAULT '#6366f1',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            date DATE NOT NULL,
            minutes INTEGER NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
        )
    ''')
    
    # Create index for faster date queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_time_entries_date 
        ON time_entries (date)
    ''')
    
    conn.commit()
    conn.close()


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    """Get all subjects."""
    db = get_db()
    subjects = db.execute('SELECT * FROM subjects ORDER BY name').fetchall()
    return jsonify([dict(s) for s in subjects])


@app.route('/api/subjects', methods=['POST'])
def create_subject():
    """Create a new subject."""
    data = request.json
    name = data.get('name', '').strip()
    color = data.get('color', '#6366f1')
    
    if not name:
        return jsonify({'error': 'Subject name is required'}), 400
    
    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO subjects (name, color) VALUES (?, ?)',
            (name, color)
        )
        db.commit()
        return jsonify({'id': cursor.lastrowid, 'name': name, 'color': color})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Subject already exists'}), 400


@app.route('/api/subjects/<int:subject_id>', methods=['DELETE'])
def delete_subject(subject_id):
    """Delete a subject and all its entries."""
    db = get_db()
    db.execute('DELETE FROM time_entries WHERE subject_id = ?', (subject_id,))
    db.execute('DELETE FROM subjects WHERE id = ?', (subject_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/entries', methods=['GET'])
def get_entries():
    """Get time entries, optionally filtered by date range."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    db = get_db()
    
    if start_date and end_date:
        entries = db.execute('''
            SELECT te.*, s.name as subject_name, s.color as subject_color
            FROM time_entries te
            JOIN subjects s ON te.subject_id = s.id
            WHERE te.date >= ? AND te.date <= ?
            ORDER BY te.date DESC, s.name
        ''', (start_date, end_date)).fetchall()
    else:
        entries = db.execute('''
            SELECT te.*, s.name as subject_name, s.color as subject_color
            FROM time_entries te
            JOIN subjects s ON te.subject_id = s.id
            ORDER BY te.date DESC, s.name
            LIMIT 100
        ''').fetchall()
    
    return jsonify([dict(e) for e in entries])


@app.route('/api/entries', methods=['POST'])
def create_entry():
    """Create a new time entry."""
    data = request.json
    subject_id = data.get('subject_id')
    entry_date = data.get('date', date.today().isoformat())
    minutes = data.get('minutes', 0)
    notes = data.get('notes', '').strip()
    
    if not subject_id:
        return jsonify({'error': 'Subject is required'}), 400
    if not minutes or minutes <= 0:
        return jsonify({'error': 'Valid time duration is required'}), 400
    
    db = get_db()
    cursor = db.execute(
        'INSERT INTO time_entries (subject_id, date, minutes, notes) VALUES (?, ?, ?, ?)',
        (subject_id, entry_date, minutes, notes)
    )
    db.commit()
    
    return jsonify({
        'id': cursor.lastrowid,
        'subject_id': subject_id,
        'date': entry_date,
        'minutes': minutes,
        'notes': notes
    })


@app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    """Delete a time entry."""
    db = get_db()
    db.execute('DELETE FROM time_entries WHERE id = ?', (entry_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics for a date range."""
    days = int(request.args.get('days', 7))
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    
    db = get_db()
    
    # Total time per subject
    subject_totals = db.execute('''
        SELECT s.id, s.name, s.color, COALESCE(SUM(te.minutes), 0) as total_minutes
        FROM subjects s
        LEFT JOIN time_entries te ON s.id = te.subject_id 
            AND te.date >= ? AND te.date <= ?
        GROUP BY s.id
        ORDER BY total_minutes DESC
    ''', (start_date.isoformat(), end_date.isoformat())).fetchall()
    
    # Daily totals
    daily_totals = db.execute('''
        SELECT date, SUM(minutes) as total_minutes
        FROM time_entries
        WHERE date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date
    ''', (start_date.isoformat(), end_date.isoformat())).fetchall()
    
    return jsonify({
        'subject_totals': [dict(s) for s in subject_totals],
        'daily_totals': [dict(d) for d in daily_totals],
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat()
    })


if __name__ == '__main__':
    print(f"Database location: {DB_PATH}")
    init_db()
    app.run(debug=True, port=5050)

