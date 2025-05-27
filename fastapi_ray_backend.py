#!/usr/bin/env python3
"""
FastAPI backend for Ray + MongoDB MCP System
Handles routing and triggers Ray jobs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import uuid
import ray
import ray_mongodb_system as ray_system
from ray_cluster_manager import get_ray_manager, ensure_ray_initialized
import logging
from collections import deque
import threading
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(title="MCP Ray Backend", version="1.0.1")

# Global task execution log
task_execution_log = deque(maxlen=50)  # Keep last 50 task executions
log_lock = threading.Lock()

def log_task_execution(session_id: str, task_name: str, worker_id: str = "unknown"):
    """Log task execution with worker information"""
    with log_lock:
        task_execution_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "task_name": task_name,
            "worker_id": worker_id
        })

@app.on_event("startup")
async def startup_event():
    """Ensure Ray is initialized on startup"""
    ray_manager = get_ray_manager()
    success = ray_manager.init_ray()
    print(f"Ray initialized: {success}")
    if success:
        print(f"Ray dashboard available at: http://127.0.0.1:8265")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of Ray on app shutdown"""
    ray_manager = get_ray_manager()
    ray_manager.cleanup()

# Add CORS middleware for Streamlit connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# State manager function
def get_state_manager():
    """Create a new state manager instance"""
    return ray_system.StateManager()

# Pydantic models
class ChatMessage(BaseModel):
    role: str
    content: str

class ProcessRequest(BaseModel):
    session_id: str
    user_input: str

class SessionResponse(BaseModel):
    session_id: str
    current_mode: str
    chat_history: List[ChatMessage]
    last_action: Optional[str] = None
    destination: Optional[str] = None

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "MCP Ray Backend is running", "status": "healthy"}

@app.post("/session/create")
async def create_session() -> SessionResponse:
    """Create a new conversation session"""
    try:
        state_manager = get_state_manager()
        state = state_manager.create_new_session()
        return SessionResponse(
            session_id=state.session_id,
            current_mode=state.current_mode,
            chat_history=[ChatMessage(role=msg.get("role", "assistant"), content=msg.get("content", "")) 
                         for msg in state.chat_history],
            last_action=state.last_action,
            destination=state.destination
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@app.get("/session/{session_id}")
async def get_session(session_id: str) -> SessionResponse:
    """Get session state"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionResponse(
            session_id=state.session_id,
            current_mode=state.current_mode,
            chat_history=[ChatMessage(role=msg.get("role", "assistant"), content=msg.get("content", "")) 
                         for msg in state.chat_history],
            last_action=state.last_action,
            destination=state.destination
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@app.post("/process")
async def process_message(request: ProcessRequest) -> SessionResponse:
    """Process user input through the Ray system"""
    try:
        session_id = request.session_id
        user_input = request.user_input
        
        # Verify session exists
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Process through Ray system
        await _process_through_ray(session_id, user_input)
        
        # Get updated state
        updated_state = get_state_manager().load_state(session_id)
        
        return SessionResponse(
            session_id=updated_state.session_id,
            current_mode=updated_state.current_mode,
            chat_history=[ChatMessage(role=msg.get("role", "assistant"), content=msg.get("content", "")) 
                         for msg in updated_state.chat_history],
            last_action=updated_state.last_action,
            destination=updated_state.destination
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")

async def _process_through_ray(session_id: str, user_input: str):
    """Internal function to process through Ray system"""
    try:
        # Ensure Ray is initialized and healthy
        if not ensure_ray_initialized():
            raise Exception("Ray is not initialized and failed to initialize")
        # Start with user input
        task_result = ray.get(ray_system.get_user_input_task.remote(session_id, user_input))
        worker_id = task_result.get("worker_info", {}).get("worker_id", "unknown")
        log_task_execution(session_id, "get_user_input_task", worker_id)
        
        # Route the request
        task_result = ray.get(ray_system.route_request_task.remote(session_id))
        worker_id = task_result.get("worker_info", {}).get("worker_id", "unknown")
        log_task_execution(session_id, "route_request_task", worker_id)
        
        # Get updated state to determine destination
        state = get_state_manager().load_state(session_id)
        destination = state.destination
        
        # Execute appropriate action based on destination
        if destination == "search_internet":
            log_task_execution(session_id, "perform_internet_search_task")
            ray.get(ray_system.perform_internet_search_task.remote(session_id))
        elif destination == "search_github":
            log_task_execution(session_id, "perform_github_search_task")
            ray.get(ray_system.perform_github_search_task.remote(session_id))
        elif destination == "search_atlassian":
            log_task_execution(session_id, "perform_atlassian_search_task")
            ray.get(ray_system.perform_atlassian_search_task.remote(session_id))
        elif destination == "search_google_maps":
            log_task_execution(session_id, "perform_google_maps_search_task")
            ray.get(ray_system.perform_google_maps_search_task.remote(session_id))
        elif destination == "search_knowledge_base":
            log_task_execution(session_id, "search_knowledge_base_task")
            ray.get(ray_system.search_knowledge_base_task.remote(session_id))
        elif destination == "search_sqlite":
            log_task_execution(session_id, "search_sqlite_task")
            ray.get(ray_system.search_sqlite_task.remote(session_id))
        elif destination == "email_assistant":
            log_task_execution(session_id, "get_email_data_task")
            ray.get(ray_system.get_email_data_task.remote(session_id))
        elif destination == "create_reply_email":
            log_task_execution(session_id, "create_reply_email_task")
            ray.get(ray_system.create_reply_email_task.remote(session_id))
        elif destination == "general_ai_response":
            task_result = ray.get(ray_system.generate_general_ai_response_task.remote(session_id))
            worker_id = task_result.get("worker_info", {}).get("worker_id", "unknown")
            log_task_execution(session_id, "generate_general_ai_response_task", worker_id)
        else:
            task_result = ray.get(ray_system.generate_general_ai_response_task.remote(session_id))
            worker_id = task_result.get("worker_info", {}).get("worker_id", "unknown")
            log_task_execution(session_id, "generate_general_ai_response_task", worker_id)
        
        # Generate final response
        log_task_execution(session_id, "generate_final_response_task")
        ray.get(ray_system.generate_final_response_task.remote(session_id))
        
        # Present response
        log_task_execution(session_id, "present_response_task")
        ray.get(ray_system.present_response_task.remote(session_id))
        
    except Exception as e:
        # Log error and re-raise
        print(f"Error in Ray processing: {str(e)}")
        raise

@app.post("/session/{session_id}/resume/{step_number}")
async def resume_from_step(session_id: str, step_number: int) -> SessionResponse:
    """Resume conversation from a specific step"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Resume from the specified step
        success = state.resume_from_step(step_number)
        if not success:
            raise HTTPException(status_code=400, detail=f"Cannot resume from step {step_number}")
        
        # Save the updated state
        state_manager.save_state(state)
        
        return SessionResponse(
            session_id=state.session_id,
            current_mode=state.current_mode,
            chat_history=[ChatMessage(role=msg.get("role", "assistant"), content=msg.get("content", "")) 
                         for msg in state.chat_history],
            last_action=state.last_action,
            destination=state.destination
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume from step: {str(e)}")

@app.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get the state history for a session"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Convert state history to a serializable format
        history = []
        for snapshot in state.state_history:
            history.append({
                "step": snapshot.step,
                "timestamp": snapshot.timestamp,
                "user_input": snapshot.user_input,
                "destination": snapshot.destination,
                "action": snapshot.action,
                "previous_state": snapshot.previous_state,
                "new_state": snapshot.new_state,
                "result_stored_in": snapshot.result_stored_in,
                "has_result": snapshot.has_result,
                "version": snapshot.version,
                "is_active": snapshot.is_active,
                "removed_at": snapshot.removed_at,
                "removed_reason": snapshot.removed_reason
            })
        
        return {
            "session_id": session_id,
            "current_step": state.current_step,
            "current_version": state.current_version,
            "total_steps_created": state.total_steps_created,
            "history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session history: {str(e)}")

@app.get("/session/{session_id}/history/{up_to_step}")
async def get_session_history_up_to_step(session_id: str, up_to_step: int):
    """Get the chat history up to and including a specific step"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Find the target step
        target_step = None
        for snapshot in state.state_history:
            if snapshot.step == up_to_step and snapshot.is_active:
                target_step = snapshot
                break
        
        if not target_step:
            raise HTTPException(status_code=404, detail=f"Step {up_to_step} not found or not active")
        
        # Calculate the ending index in chat history
        # Count how many steps up to and including this one (only active steps)
        steps_up_to = 0
        for snapshot in state.state_history:
            if snapshot.step <= up_to_step and snapshot.is_active:
                steps_up_to += 1
        
        # Each step typically adds 2 messages (user input + assistant response)
        end_index = steps_up_to * 2
        
        # Get the filtered chat history (from beginning up to the target step)
        filtered_chat_history = state.chat_history[:end_index] if end_index <= len(state.chat_history) else state.chat_history
        
        return {
            "session_id": session_id,
            "up_to_step": up_to_step,
            "chat_history": [
                {
                    "role": msg.get("role", "assistant"),
                    "content": msg.get("content", "")
                } for msg in filtered_chat_history
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session history up to step: {str(e)}")

@app.get("/ray/status")
async def get_ray_status():
    """Get Ray cluster status for monitoring"""
    try:
        ray_manager = get_ray_manager()
        cluster_info = ray_manager.get_cluster_info()
        
        # Add worker details
        worker_info = []
        if cluster_info.get('status') and ray.is_initialized():
            try:
                # Get worker information
                nodes = ray.nodes()
                for node in nodes:
                    if node.get('Alive', False):
                        node_id = node.get('NodeID', 'unknown')[:8]
                        resources = node.get('Resources', {})
                        worker_info.append({
                            'node_id': node_id,
                            'address': node.get('NodeManagerAddress', 'unknown'),
                            'hostname': node.get('NodeManagerHostname', 'unknown'),
                            'cpus': int(resources.get('CPU', 0)),
                            'memory_gb': round(resources.get('memory', 0) / 1e9, 1),
                            'status': 'alive' if node.get('Alive') else 'dead'
                        })
            except Exception as e:
                print(f"Error getting worker info: {e}")
        
        cluster_info['workers'] = worker_info
        
        return {
            "ray_healthy": ray_manager.is_healthy(),
            "cluster_info": cluster_info
        }
    except Exception as e:
        return {
            "ray_healthy": False,
            "cluster_info": {"status": False, "error": str(e)},
            "error": str(e)
        }

@app.get("/servers/status")
async def get_server_status():
    """Get status of all MCP servers"""
    servers = {
        "General AI": "general",
        "Internet Search": "internet_search", 
        "GitHub": "github_search",
        "Atlassian": "atlassian_search",
        "Knowledge Base": "knowledge_base_search",
        "Google Maps": "google_maps_search",
        "SQLite": "sqlite_search",
        "Email Assistant": "email_assistant"
    }
    
    return {"servers": servers, "status": "available"}

@app.get("/ray/task-logs/{session_id}")
async def get_task_logs(session_id: str):
    """Get recent task execution logs for a session"""
    with log_lock:
        session_logs = [
            log for log in task_execution_log 
            if log["session_id"] == session_id
        ]
        return {"logs": list(session_logs)}

@app.get("/ray/task-logs")
async def get_all_task_logs():
    """Get all recent task execution logs"""
    with log_lock:
        return {"logs": list(task_execution_log)}

@app.get("/session/{session_id}/timeline")
async def get_session_timeline(session_id: str):
    """Get the conversation timeline with active and removed steps"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        timeline_summary = state.get_timeline_summary()
        return {
            "session_id": session_id,
            "timeline": timeline_summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session timeline: {str(e)}")

@app.get("/session/{session_id}/steps/active")
async def get_active_steps(session_id: str):
    """Get only the active steps in the current timeline"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        active_steps = state.get_active_steps()
        return {
            "session_id": session_id,
            "current_version": state.current_version,
            "active_steps": [
                {
                    "step": s.step,
                    "timestamp": s.timestamp,
                    "user_input": s.user_input,
                    "action": s.action,
                    "destination": s.destination,
                    "has_result": s.has_result,
                    "version": s.version
                } for s in active_steps
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active steps: {str(e)}")

@app.get("/session/{session_id}/steps/removed")
async def get_removed_steps(session_id: str):
    """Get all removed steps for observability"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        removed_steps = state.get_removed_steps()
        return {
            "session_id": session_id,
            "removed_steps": [
                {
                    "step": s.step,
                    "timestamp": s.timestamp,
                    "user_input": s.user_input,
                    "action": s.action,
                    "destination": s.destination,
                    "has_result": s.has_result,
                    "version": s.version,
                    "removed_at": s.removed_at,
                    "removed_reason": s.removed_reason
                } for s in removed_steps
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get removed steps: {str(e)}")

@app.get("/session/{session_id}/step/{step_number}")
async def get_step_details(session_id: str, step_number: int, include_removed: bool = False):
    """Get detailed information about a specific step"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        step = state.get_step_by_number(step_number, include_removed)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")
        
        # Get all results from this step
        results = {}
        result_types = [
            'internet_search_results', 'github_search_results', 'general_ai_response',
            'atlassian_search_results', 'knowledge_base_results', 'gmaps_results',
            'sqlite_search_results', 'email_response', 'final_response'
        ]
        
        for result_type in result_types:
            if hasattr(step, result_type):
                result = getattr(step, result_type, None)
                if result:
                    results[result_type] = result
        
        return {
            "session_id": session_id,
            "step": {
                "step": step.step,
                "timestamp": step.timestamp,
                "user_input": step.user_input,
                "action": step.action,
                "destination": step.destination,
                "has_result": step.has_result,
                "version": step.version,
                "is_active": step.is_active,
                "removed_at": step.removed_at,
                "removed_reason": step.removed_reason,
                "results": results
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get step details: {str(e)}")

@app.get("/session/{session_id}/graph")
async def get_session_graph(session_id: str):
    """Get conversation timeline as graph data for visualization"""
    try:
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Build graph data structure with improved layout
        nodes = []
        edges = []
        
        # Add start node
        nodes.append({
            "id": "start",
            "label": "Start",
            "type": "start",
            "color": "#4CAF50",
            "size": 25,
            "x": 0,
            "y": 0
        })
        
        # Process all steps and organize by timeline
        all_steps = sorted(state.state_history, key=lambda x: (x.step, x.version))
        
        # Improved layout calculation
        step_spacing_x = 200
        version_spacing_y = 120
        branch_offset_y = 60
        
        # Separate active and removed steps for better layout
        active_steps = [s for s in all_steps if s.is_active]
        removed_steps = [s for s in all_steps if not s.is_active]
        
        # Create main timeline (active steps)
        main_timeline_y = 0
        
        # Position active steps along main timeline
        for i, step in enumerate(sorted(active_steps, key=lambda x: x.step)):
            x = (step.step) * step_spacing_x
            y = main_timeline_y
            
            # Determine node properties
            color = "#2196F3" if step.has_result else "#FF9800"
            border_color = "#1976D2" if step.has_result else "#F57C00"
            
            # Create cleaner action label
            action_parts = step.action.replace("_", " ").split()
            action_label = " ".join(word.capitalize() for word in action_parts)
            
            # Shorter, cleaner node label
            node_label = f"Step {step.step}\n{action_label}"
            
            nodes.append({
                "id": f"step_{step.step}_{step.version}",
                "label": node_label,
                "type": "step",
                "step_number": step.step,
                "version": step.version,
                "action": step.action,
                "destination": step.destination,
                "has_result": step.has_result,
                "is_active": step.is_active,
                "timestamp": step.timestamp,
                "user_input": step.user_input[:100] + "..." if len(step.user_input) > 100 else step.user_input,
                "removed_at": None,
                "removed_reason": None,
                "color": color,
                "border_color": border_color,
                "opacity": 1.0,
                "size": 30,
                "x": x,
                "y": y
            })
        
        # Position removed steps in branches below main timeline
        removed_by_branch = {}
        for step in removed_steps:
            # Group removed steps by the step they were removed from
            if step.removed_reason and "Resumed from step" in step.removed_reason:
                try:
                    resume_step_num = int(step.removed_reason.split("step ")[-1])
                    if resume_step_num not in removed_by_branch:
                        removed_by_branch[resume_step_num] = []
                    removed_by_branch[resume_step_num].append(step)
                except:
                    # Fallback for parsing errors
                    if "other" not in removed_by_branch:
                        removed_by_branch["other"] = []
                    removed_by_branch["other"].append(step)
        
        # Position removed steps in organized branches
        branch_index = 1
        for resume_step, branch_steps in removed_by_branch.items():
            branch_y = -branch_index * (version_spacing_y + branch_offset_y)
            
            for i, step in enumerate(sorted(branch_steps, key=lambda x: x.step)):
                x = step.step * step_spacing_x
                y = branch_y
                
                # Removed step styling
                color = "#9E9E9E"
                border_color = "#757575"
                
                # Create action label
                action_parts = step.action.replace("_", " ").split()
                action_label = " ".join(word.capitalize() for word in action_parts)
                
                node_label = f"Step {step.step}.{step.version}\n{action_label}\n(Removed)"
                
                nodes.append({
                    "id": f"step_{step.step}_{step.version}",
                    "label": node_label,
                    "type": "step",
                    "step_number": step.step,
                    "version": step.version,
                    "action": step.action,
                    "destination": step.destination,
                    "has_result": step.has_result,
                    "is_active": step.is_active,
                    "timestamp": step.timestamp,
                    "user_input": step.user_input[:100] + "..." if len(step.user_input) > 100 else step.user_input,
                    "removed_at": step.removed_at,
                    "removed_reason": step.removed_reason,
                    "color": color,
                    "border_color": border_color,
                    "opacity": 0.7,
                    "size": 25,
                    "x": x,
                    "y": y,
                    "branch_index": branch_index,
                    "resume_step": resume_step
                })
            
            branch_index += 1
        
        # Create cleaner edge connections
        
        # 1. Connect start to first active step
        if active_steps:
            first_step = min(active_steps, key=lambda x: x.step)
            edges.append({
                "id": f"start_to_step_{first_step.step}",
                "source": "start",
                "target": f"step_{first_step.step}_{first_step.version}",
                "type": "main_flow",
                "color": "#4CAF50",
                "width": 3,
                "opacity": 1.0,
                "style": "solid"
            })
        
        # 2. Connect sequential active steps (main timeline)
        sorted_active = sorted(active_steps, key=lambda x: x.step)
        for i in range(len(sorted_active) - 1):
            current_step = sorted_active[i]
            next_step = sorted_active[i + 1]
            
            edges.append({
                "id": f"main_flow_{current_step.step}_to_{next_step.step}",
                "source": f"step_{current_step.step}_{current_step.version}",
                "target": f"step_{next_step.step}_{next_step.version}",
                "type": "main_flow",
                "color": "#2196F3",
                "width": 3,
                "opacity": 1.0,
                "style": "solid"
            })
        
        # 3. Connect removed step branches
        for resume_step, branch_steps in removed_by_branch.items():
            if isinstance(resume_step, int):
                # Find the resume point in active steps
                resume_node = next((s for s in active_steps if s.step == resume_step), None)
                if resume_node:
                    # Connect resume point to branch
                    sorted_branch = sorted(branch_steps, key=lambda x: x.step)
                    if sorted_branch:
                        # Connect to first step in branch
                        first_branch_step = sorted_branch[0]
                        edges.append({
                            "id": f"branch_from_{resume_step}_to_{first_branch_step.step}",
                            "source": f"step_{resume_node.step}_{resume_node.version}",
                            "target": f"step_{first_branch_step.step}_{first_branch_step.version}",
                            "type": "branch_point",
                            "color": "#FF5722",
                            "width": 2,
                            "opacity": 0.8,
                            "style": "dashed"
                        })
                        
                        # Connect sequential steps within branch
                        for i in range(len(sorted_branch) - 1):
                            current_step = sorted_branch[i]
                            next_step = sorted_branch[i + 1]
                            
                            if next_step.step == current_step.step + 1:  # Only connect sequential steps
                                edges.append({
                                    "id": f"branch_flow_{current_step.step}_to_{next_step.step}",
                                    "source": f"step_{current_step.step}_{current_step.version}",
                                    "target": f"step_{next_step.step}_{next_step.version}",
                                    "type": "branch_flow",
                                    "color": "#9E9E9E",
                                    "width": 2,
                                    "opacity": 0.6,
                                    "style": "solid"
                                })
        
        # Calculate improved graph statistics
        graph_stats = {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "total_steps": len(all_steps),
            "active_steps": len(active_steps),
            "removed_steps": len(removed_steps),
            "current_version": state.current_version,
            "current_step": state.current_step,
            "versions": len(set(s.version for s in all_steps)),
            "branches": len(removed_by_branch)
        }
        
        return {
            "session_id": session_id,
            "graph": {
                "nodes": nodes,
                "edges": edges
            },
            "stats": graph_stats,
            "layout": {
                "type": "improved_hierarchical",
                "direction": "LR",  # Left to Right
                "step_spacing_x": step_spacing_x,
                "version_spacing_y": version_spacing_y,
                "branch_offset_y": branch_offset_y,
                "main_timeline_y": main_timeline_y
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate graph data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 