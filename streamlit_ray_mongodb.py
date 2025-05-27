import uuid
import asyncio
import streamlit as st
import requests
import json
from typing import Dict, List, Optional
import ray
from pymongo import MongoClient
import os

# FastAPI backend URL
BACKEND_URL = "http://localhost:8000"

# MongoDB and Ray configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "mcp_system")

def render_chat_message(chat_item: dict):
    content = chat_item["content"]
    role = chat_item.get("role", "assistant")

    with st.chat_message(role):
        st.write(content)


def initialize_session():
    """Initialize session with FastAPI backend"""
    if "session_id" not in st.session_state:
        try:
            response = requests.post(f"{BACKEND_URL}/session/create")
            if response.status_code == 200:
                session_data = response.json()
                st.session_state.session_id = session_data["session_id"]
                st.session_state.session_data = session_data
            else:
                st.error("Failed to create session with backend")
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.session_data = {
                    "session_id": st.session_state.session_id,
                    "current_mode": "general",
                    "chat_history": [],
                    "last_action": None,
                    "destination": None
                }
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to FastAPI backend. Please ensure it's running on port 8000.")
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.session_data = {
                "session_id": st.session_state.session_id,
                "current_mode": "general", 
                "chat_history": [],
                "last_action": None,
                "destination": None
            }
    
    return st.session_state.session_data


def get_session_data():
    """Get current session data from backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}")
        if response.status_code == 200:
            st.session_state.session_data = response.json()
            return st.session_state.session_data
        else:
            return st.session_state.session_data
    except requests.exceptions.ConnectionError:
        return st.session_state.session_data


@st.cache_data(ttl=10)  # Cache for 10 seconds
def check_mongodb_status():
    """Check MongoDB connection status"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.server_info()  # Will raise an exception if can't connect
        client.close()
        return True
    except Exception:
        return False


@st.cache_data(ttl=10)  # Cache for 10 seconds
def check_ray_status():
    """Check Ray cluster status"""
    try:
        # Try to initialize Ray if not already initialized
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True, address="auto", _node_ip_address="127.0.0.1")
        
        # Check if Ray is working by getting cluster resources
        resources = ray.cluster_resources()
        return len(resources) > 0
    except Exception:
        return False


@st.cache_data(ttl=5)  # Cache for 5 seconds
def check_backend_status():
    """Check FastAPI backend status"""
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=2)
        return response.status_code == 200
    except:
        return False


def show_server_status(session_data):
    """Display server status in the sidebar with indicators."""
    
    # Get current mode from session data
    current_mode = session_data.get("current_mode", "general")
    
    # Define all available servers
    servers = {
        "General AI": "general",
        "Internet Search": "internet_search",
        "GitHub": "github_search",
        "Atlassian": "atlassian_search",
        "Knowledge Base": "knowledge_base_search",
        "Google Maps": "google_maps_search",
        "SQLite": "sqlite_search"
    }
    
    # Create the sidebar
    st.sidebar.title("MCP Server Status")
    
    st.logo(
        "documentation/haptiq.png",
    )
    
    # List all servers with indicators
    for server_name, mode in servers.items():
        # Check if this server is active
        is_active = current_mode == mode
        
        # Create the indicator color
        indicator = "🟢" if is_active else "⚪"
        
        # Show the server with its indicator
        st.sidebar.markdown(f"{indicator} {server_name}")
    
    st.sidebar.title("Tools and Apps Status")
    
    # Check if email assistant is active
    if current_mode == "email_assistant":
        st.sidebar.markdown("🟢 Email Assistant")
    else:
        st.sidebar.markdown("⚪ Email Assistant")
        
    # Add a divider
    st.sidebar.divider()
    
    # Show conversation history if available
    try:
        if st.session_state.session_id:
            response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}/history")
            if response.status_code == 200:
                history_data = response.json()
                if history_data.get("history"):
                    st.sidebar.title("📚 Conversation History")
                    st.sidebar.caption(f"Current Step: {history_data.get('current_step', 0)}")
                    
                    for step in history_data["history"]:
                        step_num = step["step"]
                        action = step["action"].replace("_", " ").title()
                        has_result = "✅" if step["has_result"] else "❌"
                        
                        if st.sidebar.button(f"Step {step_num}: {action} {has_result}", 
                                           key=f"step_{step_num}",
                                           help=f"Resume from: {step['user_input'][:50]}..."):
                            # Resume from this step
                            resume_response = requests.post(f"{BACKEND_URL}/session/{st.session_state.session_id}/resume/{step_num}")
                            if resume_response.status_code == 200:
                                st.session_state.session_data = resume_response.json()
                                st.rerun()
                    
                    st.sidebar.divider()
    except:
        pass
    
    # Show system status
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        st.markdown("### 🔧 System Status")
    with col2:
        if st.button("🔄", help="Refresh status", key="refresh_status"):
            # Clear cache to force refresh
            check_backend_status.clear()
            check_mongodb_status.clear()
            check_ray_status.clear()
    
    # Backend status
    if check_backend_status():
        st.sidebar.success("✅ FastAPI Backend")
    else:
        st.sidebar.error("❌ FastAPI Backend")
    
    # MongoDB status
    if check_mongodb_status():
        st.sidebar.success("✅ MongoDB Connected")
    else:
        st.sidebar.error("❌ MongoDB Disconnected")
    
    # Ray status
    if check_ray_status():
        st.sidebar.success("✅ Ray Cluster Active")
        try:
            if ray.is_initialized():
                resources = ray.cluster_resources()
                cpu_count = resources.get('CPU', 0)
                st.sidebar.caption(f"CPUs: {int(cpu_count)}")
        except:
            pass
    else:
        st.sidebar.error("❌ Ray Cluster Inactive")
    
    # Additional system info
    st.sidebar.caption(f"MongoDB URI: {MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI}")
    st.sidebar.caption(f"Database: {DB_NAME}")


async def process_user_input(user_input: str):
    """Process user input through the FastAPI backend"""
    try:
        # Send request to FastAPI backend
        payload = {
            "session_id": st.session_state.session_id,
            "user_input": user_input
        }
        
        response = requests.post(f"{BACKEND_URL}/process", json=payload)
        
        if response.status_code == 200:
            # Update session data with response
            st.session_state.session_data = response.json()
        else:
            st.error(f"Backend error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to FastAPI backend. Please ensure it's running.")
    except Exception as e:
        st.error(f"Error processing request: {str(e)}")


async def main():
    st.title("Ray + MongoDB MCP System")
    session_data = initialize_session()
    
    # Show server status in sidebar
    show_server_status(session_data)
    
    # Display chat history
    chat_history = session_data.get("chat_history", [])
    for chat_message in chat_history:
        render_chat_message(chat_message)

    # Get user input
    prompt = st.chat_input("Ask me a question!", key="chat_input")

    if prompt:
        # Process through FastAPI backend
        with st.spinner("Processing your request..."):
            await process_user_input(prompt)
        st.rerun()


if __name__ == "__main__":
    # This remains for Streamlit's async entry point handling
    asyncio.run(main()) 