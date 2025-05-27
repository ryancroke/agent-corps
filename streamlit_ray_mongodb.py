import uuid
import asyncio
import streamlit as st
import requests
import json
from typing import Dict, List, Optional
import ray
from pymongo import MongoClient
import os
from ray_cluster_manager import get_ray_manager

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


@st.cache_data(ttl=5)  # Cache for 5 seconds
def get_ray_cluster_info():
    """Get detailed Ray cluster information via FastAPI backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/ray/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("cluster_info", {
                'status': False,
                'error': 'No cluster info',
                'resources': {},
                'nodes': [],
                'tasks': [],
                'num_cpus': 0,
                'num_nodes': 0,
                'num_workers': 0
            })
        return {
            'status': False,
            'error': 'Backend not responding',
            'resources': {},
            'nodes': [],
            'tasks': [],
            'num_cpus': 0,
            'num_nodes': 0,
            'num_workers': 0
        }
    except Exception as e:
        print(f"Ray cluster info error: {e}")
        return {
            'status': False,
            'error': str(e),
            'resources': {},
            'nodes': [],
            'tasks': [],
            'num_cpus': 0,
            'num_nodes': 0,
            'num_workers': 0
        }

@st.cache_data(ttl=10)  # Cache for 10 seconds  
def check_ray_status():
    """Check Ray cluster status via FastAPI backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/ray/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("ray_healthy", False)
        return False
    except Exception as e:
        print(f"Ray status check error: {e}")
        return False


@st.cache_data(ttl=5)  # Cache for 5 seconds
def check_backend_status():
    """Check FastAPI backend status"""
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=2)
        return response.status_code == 200
    except:
        return False

def get_session_ray_tasks(session_id):
    """Get Ray tasks related to the current session"""
    try:
        ray_info = get_ray_cluster_info()
        session_tasks = []
        
        for task in ray_info['tasks']:
            # Check if task name suggests it's related to our session
            # (This is a heuristic - in production you'd want better task tracking)
            if any(keyword in task['name'].lower() for keyword in [
                'route_request', 'perform_internet_search', 'perform_github_search',
                'perform_atlassian_search', 'generate_general_ai_response',
                'search_knowledge_base', 'search_sqlite', 'perform_google_maps_search'
            ]):
                session_tasks.append(task)
        
        return session_tasks
    except:
        return []

def show_ray_dashboard():
    """Show detailed Ray cluster dashboard"""
    st.sidebar.markdown("### 🔬 Ray Cluster Dashboard")
    
    ray_info = get_ray_cluster_info()
    
    if not ray_info['status']:
        st.sidebar.error("❌ Ray cluster not available")
        if 'error' in ray_info:
            st.sidebar.caption(f"Error: {ray_info['error']}")
        return
    
    # Cluster overview metrics
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.sidebar.metric("Nodes", ray_info['num_nodes'])
        st.sidebar.metric("Workers", ray_info['num_workers'])
    with col2:
        st.sidebar.metric("CPUs", ray_info['num_cpus'])
        st.sidebar.metric("Active Tasks", len(ray_info['tasks']))
    
    # Resource utilization
    if ray_info['resources']:
        st.sidebar.markdown("**📊 Resource Usage:**")
        total_cpus = ray_info['resources'].get('CPU', 0)
        used_cpus = len(ray_info['tasks'])  # Approximation
        if total_cpus > 0:
            utilization = min(used_cpus / total_cpus, 1.0)
            st.sidebar.progress(utilization, text=f"CPU: {used_cpus}/{int(total_cpus)}")
    
    # Live task monitoring
    if ray_info['tasks']:
        st.sidebar.markdown("**🔄 Live Task Monitor:**")
        for task in ray_info['tasks']:
            task_name = task['name'].replace('ray_mongodb_system.', '').replace('_task', '')
            state_color = "🟢" if task['state'] == 'RUNNING' else "🟡"
            
            with st.sidebar.expander(f"{state_color} {task_name}", expanded=False):
                st.write(f"**Task ID:** `{task['task_id']}`")
                st.write(f"**State:** {task['state']}")
                st.write(f"**Worker:** `{task['worker_id']}`")
                st.write(f"**Node:** `{task['node_id']}`")
    
    # Node details
    if ray_info['nodes']:
        st.sidebar.markdown("**🖥️ Node Details:**")
        for i, node in enumerate(ray_info['nodes']):
            if node.get('Alive', False):
                node_id = node.get('NodeID', 'unknown')[:8]
                resources = node.get('Resources', {})
                cpu = int(resources.get('CPU', 0))
                memory = resources.get('memory', 0)
                
                with st.sidebar.expander(f"Node {i+1}: {node_id}", expanded=False):
                    st.write(f"**IP:** {node.get('NodeManagerAddress', 'unknown')}")
                    st.write(f"**CPUs:** {cpu}")
                    if memory:
                        st.write(f"**Memory:** {memory/1e9:.1f} GB")
                    st.write(f"**Status:** {'🟢 Alive' if node.get('Alive') else '🔴 Dead'}")
    
    # Control buttons
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🔄 Refresh", help="Manually refresh Ray cluster information"):
            get_ray_cluster_info.clear()
            st.rerun()
    with col2:
        if st.button("🔁 Restart", help="Restart Ray cluster"):
            ray_manager = get_ray_manager()
            with st.spinner("Restarting Ray..."):
                success = ray_manager.restart()
            if success:
                st.success("Ray restarted successfully!")
            else:
                st.error("Failed to restart Ray")
            get_ray_cluster_info.clear()
            st.rerun()


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
    
    # Show enhanced conversation timeline if available
    try:
        if st.session_state.session_id:
            # Get timeline data
            timeline_response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}/timeline")
            if timeline_response.status_code == 200:
                timeline_data = timeline_response.json()["timeline"]
                
                if timeline_data.get("active_steps") or timeline_data.get("removed_steps"):
                    st.sidebar.title("📚 Conversation Timeline")
                    
                    # Show timeline summary
                    col1, col2 = st.sidebar.columns(2)
                    with col1:
                        st.sidebar.caption(f"🔄 Version: {timeline_data.get('current_version', 1)}")
                        st.sidebar.caption(f"📍 Current Step: {timeline_data.get('current_step', 0)}")
                    with col2:
                        st.sidebar.caption(f"✅ Active: {timeline_data.get('active_steps_count', 0)}")
                        st.sidebar.caption(f"🗑️ Removed: {timeline_data.get('removed_steps_count', 0)}")
                    
                    # Show active steps
                    if timeline_data.get("active_steps"):
                        st.sidebar.markdown("**🟢 Active Timeline:**")
                        for step in timeline_data["active_steps"]:
                            step_num = step["step"]
                            action = step["action"].replace("_", " ").title()
                            has_result = "✅" if step["has_result"] else "❌"
                            version = step.get("version", 1)
                            
                            # Create button with version info
                            button_text = f"Step {step_num}.{version}: {action} {has_result}"
                            if st.sidebar.button(button_text, 
                                               key=f"active_step_{step_num}",
                                               help=f"Resume from: {step.get('user_input', 'N/A')[:50]}..."):
                                # Resume from this step
                                resume_response = requests.post(f"{BACKEND_URL}/session/{st.session_state.session_id}/resume/{step_num}")
                                if resume_response.status_code == 200:
                                    st.session_state.session_data = resume_response.json()
                                    st.success(f"Resumed from step {step_num}")
                                    st.rerun()
                                else:
                                    st.error("Failed to resume from step")
                    
                    # Show removed steps in an expander for observability
                    if timeline_data.get("removed_steps"):
                        with st.sidebar.expander(f"🗑️ Removed Steps ({len(timeline_data['removed_steps'])})", expanded=False):
                            for step in timeline_data["removed_steps"]:
                                step_num = step["step"]
                                action = step["action"].replace("_", " ").title()
                                version = step.get("version", 1)
                                removed_reason = step.get("removed_reason", "Unknown")
                                
                                st.write(f"**Step {step_num}.{version}:** {action}")
                                st.caption(f"Removed: {removed_reason}")
                                st.caption(f"At: {step.get('removed_at', 'Unknown')[-8:]}")
                    
                    st.sidebar.divider()
    except Exception as e:
        print(f"Timeline error: {e}")
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
    
    # Ray status with detailed information
    ray_info = get_ray_cluster_info()
    if ray_info['status']:
        st.sidebar.success("✅ Ray Cluster Active")
        
        # Show cluster overview
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.sidebar.caption(f"🖥️ Nodes: {ray_info['num_nodes']}")
            st.sidebar.caption(f"⚡ CPUs: {ray_info['num_cpus']}")
        with col2:
            st.sidebar.caption(f"👷 Workers: {ray_info['num_workers']}")
            st.sidebar.caption(f"🔄 Tasks: {len(ray_info['tasks'])}")
        
        # Show worker details
        workers = ray_info.get('workers', [])
        if workers:
            st.sidebar.markdown("**👷 Available Workers:**")
            for i, worker in enumerate(workers):
                worker_status = "🟢" if worker['status'] == 'alive' else "🔴"
                st.sidebar.caption(f"{worker_status} Worker {i+1}: `{worker['node_id']}`")
                st.sidebar.caption(f"   📍 {worker['hostname']} ({worker['address']})")
                st.sidebar.caption(f"   💾 {worker['cpus']} CPUs, {worker['memory_gb']} GB RAM")
        
        # Show recent task executions for this session
        try:
            if st.session_state.session_id:
                response = requests.get(f"{BACKEND_URL}/ray/task-logs/{st.session_state.session_id}", timeout=2)
                if response.status_code == 200:
                    logs_data = response.json()
                    logs = logs_data.get("logs", [])
                    if logs:
                        st.sidebar.markdown("**🎯 Recent Task Executions:**")
                        for log in logs[-3:]:  # Show last 3 tasks
                            task_name = log["task_name"].replace("_task", "").replace("_", " ").title()
                            timestamp = log["timestamp"][:19].replace("T", " ")
                            worker_id = log["worker_id"]
                            st.sidebar.caption(f"🔄 {task_name}")
                            st.sidebar.caption(f"   👷 Worker: `{worker_id}` at {timestamp[-8:]}")
        except:
            pass
        
        # Show session-specific tasks first
        session_tasks = get_session_ray_tasks(st.session_state.get('session_id', ''))
        if session_tasks:
            st.sidebar.markdown("**🎯 Your Session Tasks:**")
            for task in session_tasks:
                task_name = task['name'].replace('ray_mongodb_system.', '').replace('_task', '')
                state_emoji = "🟡" if task['state'] == 'RUNNING' else "🔵"
                st.sidebar.caption(f"{state_emoji} {task_name}")
                st.sidebar.caption(f"   Worker: {task['worker_id']}")
        
        # Show all active tasks if any
        if ray_info['tasks']:
            remaining_tasks = [t for t in ray_info['tasks'] if t not in session_tasks]
            if remaining_tasks:
                st.sidebar.markdown("**🔄 Other Active Tasks:**")
                for task in remaining_tasks[:2]:  # Show max 2 other tasks
                    task_name = task['name'].replace('ray_mongodb_system.', '').replace('_task', '')
                    state_emoji = "🟡" if task['state'] == 'RUNNING' else "🔵"
                    st.sidebar.caption(f"{state_emoji} {task_name}")
                    st.sidebar.caption(f"   Worker: {task['worker_id']}")
                
                if len(remaining_tasks) > 2:
                    st.sidebar.caption(f"   ... and {len(remaining_tasks) - 2} more")
        
        # Show worker details in an expander
        with st.sidebar.expander("🔍 Ray Cluster Details"):
            st.write("**Nodes:**")
            for i, node in enumerate(ray_info['nodes']):
                if node.get('Alive', False):
                    node_id = node.get('NodeID', 'unknown')[:8]
                    node_ip = node.get('NodeManagerAddress', 'unknown')
                    resources = node.get('Resources', {})
                    cpu = int(resources.get('CPU', 0))
                    st.write(f"• Node {i+1}: `{node_id}` ({node_ip})")
                    st.write(f"  CPUs: {cpu}")
            
            if ray_info['tasks']:
                st.write("**All Active Tasks:**")
                for task in ray_info['tasks']:
                    st.write(f"• `{task['task_id']}`: {task['name']}")
                    st.write(f"  State: {task['state']}, Worker: `{task['worker_id']}`")
    else:
        st.sidebar.error("❌ Ray Cluster Inactive")
        if 'error' in ray_info:
            st.sidebar.caption(f"Error: {ray_info['error'][:50]}...")
    
    # Additional system info
    st.sidebar.caption(f"MongoDB URI: {MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI}")
    st.sidebar.caption(f"Database: {DB_NAME}")
    
    # Ray Dashboard Toggle
    st.sidebar.divider()
    if st.sidebar.checkbox("🔬 Ray Dashboard", value=False, help="Show detailed Ray cluster monitoring"):
        show_ray_dashboard()


async def process_user_input(user_input: str):
    """Process user input through the FastAPI backend"""
    try:
        # Create placeholders for real-time monitoring
        task_status_placeholder = st.empty()
        worker_status_placeholder = st.empty()
        
        # Show initial processing status
        with task_status_placeholder.container():
            st.info("🚀 Starting Ray tasks...")
        
        # Show worker assignment
        ray_info = get_ray_cluster_info()
        if ray_info.get('status') and ray_info.get('workers'):
            with worker_status_placeholder.container():
                st.info(f"👷 Assigning to {len(ray_info['workers'])} available worker(s)")
        
        # Send request to FastAPI backend
        payload = {
            "session_id": st.session_state.session_id,
            "user_input": user_input
        }
        
        response = requests.post(f"{BACKEND_URL}/process", json=payload)
        
        if response.status_code == 200:
            # Update session data with response
            st.session_state.session_data = response.json()
            
            # Show completion status
            with task_status_placeholder.container():
                st.success("✅ Ray tasks completed successfully!")
            
            # Clear status after a moment
            import time
            time.sleep(1)
            task_status_placeholder.empty()
            worker_status_placeholder.empty()
        else:
            task_status_placeholder.empty()
            worker_status_placeholder.empty()
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