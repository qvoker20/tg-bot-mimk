#!/usr/bin/env python
"""Debug script to check if 18:00 trigger ran."""
from app.modules.assemblers.db.connection import get_db_connection

with get_db_connection() as conn:
    with conn.cursor() as cursor:
        # Check today's date in Kyiv timezone
        cursor.execute("SELECT NOW() AT TIME ZONE 'Europe/Kyiv' as kyiv_now")
        kyiv_now = cursor.fetchone()[0]
        print(f'Current time (Kyiv): {kyiv_now}')
        print()
        
        # Check if today's cutoff already ran
        cursor.execute('SELECT run_date, processed_at FROM assemblers_schedule_auto_close_runs ORDER BY run_date DESC LIMIT 5')
        rows = cursor.fetchall()
        print('Last 5 auto-close runs:')
        for run_date, processed_at in rows:
            print(f'  Run date: {run_date}, Processed at: {processed_at}')
        print()
        
        # Check pending tasks for today
        today = kyiv_now.date()
        cursor.execute(
            'SELECT COUNT(*), status FROM assemblers_schedule_tasks WHERE scheduled_for = %s GROUP BY status ORDER BY status',
            (today,)
        )
        rows = cursor.fetchall()
        print(f'Tasks for today ({today}):')
        for count, status in rows:
            print(f'  {status}: {count}')
        print()
        
        # Check if there were any tasks to close yesterday
        yesterday = (kyiv_now.replace(day=kyiv_now.day-1) if kyiv_now.day > 1 else kyiv_now.replace(month=kyiv_now.month-1, day=28)).date()
        cursor.execute(
            'SELECT COUNT(*), status FROM assemblers_schedule_tasks WHERE scheduled_for = %s GROUP BY status ORDER BY status',
            (yesterday,)
        )
        rows = cursor.fetchall()
        print(f'Tasks for yesterday ({yesterday}):')
        for count, status in rows:
            print(f'  {status}: {count}')
