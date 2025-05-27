#!/usr/bin/env python3
"""
Task logging module for Ray worker pool system
Avoids circular import issues between workflow orchestrator and FastAPI backend
"""

from collections import deque
import threading
from datetime import datetime
from typing import Dict, List

# Global task execution log
task_execution_log = deque(maxlen=100)  # Keep last 100 task executions
log_lock = threading.Lock()

def log_task_execution(session_id: str, task_name: str, worker_id: str = "unknown", worker_type: str = "unknown"):
    """Log task execution with worker information"""
    with log_lock:
        task_execution_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "task_name": task_name,
            "worker_id": worker_id,
            "worker_type": worker_type,
            "status": "completed"
        })

def get_task_logs(session_id: str = None) -> List[Dict]:
    """Get task execution logs, optionally filtered by session"""
    with log_lock:
        if session_id:
            return [
                log for log in task_execution_log 
                if log["session_id"] == session_id
            ]
        return list(task_execution_log)

def clear_logs():
    """Clear all task logs"""
    with log_lock:
        task_execution_log.clear()

def get_log_stats() -> Dict:
    """Get statistics about task execution logs"""
    with log_lock:
        logs = list(task_execution_log)
        
        if not logs:
            return {
                "total_tasks": 0,
                "unique_sessions": 0,
                "worker_types": {},
                "task_types": {}
            }
        
        # Count by worker type
        worker_types = {}
        for log in logs:
            worker_type = log.get("worker_type", "unknown")
            worker_types[worker_type] = worker_types.get(worker_type, 0) + 1
        
        # Count by task type
        task_types = {}
        for log in logs:
            task_name = log.get("task_name", "unknown")
            task_types[task_name] = task_types.get(task_name, 0) + 1
        
        # Count unique sessions
        unique_sessions = len(set(log.get("session_id", "") for log in logs))
        
        return {
            "total_tasks": len(logs),
            "unique_sessions": unique_sessions,
            "worker_types": worker_types,
            "task_types": task_types
        } 