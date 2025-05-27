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

# Initialize FastAPI app
app = FastAPI(title="MCP Ray Backend", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Ensure Ray is initialized on startup"""
    global ray_initialized
    if not ray_initialized:
        ray_initialized = init_ray()
    print(f"Ray initialized: {ray_initialized}")

# Add CORS middleware for Streamlit connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Ray (if not already initialized)
def init_ray():
    """Initialize Ray with proper error handling"""
    try:
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True, address="auto", _node_ip_address="127.0.0.1")
        return True
    except Exception as e:
        print(f"Ray initialization failed: {e}")
        return False

# Initialize Ray on startup
ray_initialized = init_ray()

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
        # Ensure Ray is initialized
        if not ray.is_initialized():
            global ray_initialized
            ray_initialized = init_ray()
            if not ray_initialized:
                raise Exception("Ray is not initialized and failed to initialize")
        # Start with user input
        ray.get(ray_system.get_user_input_task.remote(session_id, user_input))
        
        # Route the request
        ray.get(ray_system.route_request_task.remote(session_id))
        
        # Get updated state to determine destination
        state = get_state_manager().load_state(session_id)
        destination = state.destination
        
        # Execute appropriate action based on destination
        if destination == "search_internet":
            ray.get(ray_system.perform_internet_search_task.remote(session_id))
        elif destination == "search_github":
            ray.get(ray_system.perform_github_search_task.remote(session_id))
        elif destination == "search_atlassian":
            ray.get(ray_system.perform_atlassian_search_task.remote(session_id))
        elif destination == "search_google_maps":
            ray.get(ray_system.perform_google_maps_search_task.remote(session_id))
        elif destination == "search_knowledge_base":
            ray.get(ray_system.search_knowledge_base_task.remote(session_id))
        elif destination == "search_sqlite":
            ray.get(ray_system.search_sqlite_task.remote(session_id))
        elif destination == "email_assistant":
            ray.get(ray_system.get_email_data_task.remote(session_id))
        elif destination == "create_reply_email":
            ray.get(ray_system.create_reply_email_task.remote(session_id))
        elif destination == "general_ai_response":
            ray.get(ray_system.generate_general_ai_response_task.remote(session_id))
        else:
            ray.get(ray_system.generate_general_ai_response_task.remote(session_id))
        
        # Generate final response
        ray.get(ray_system.generate_final_response_task.remote(session_id))
        
        # Present response
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
                "has_result": snapshot.has_result
            })
        
        return {
            "session_id": session_id,
            "current_step": state.current_step,
            "history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session history: {str(e)}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 