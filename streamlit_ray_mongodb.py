import uuid
import asyncio
import streamlit as st
import requests
import json
import time
from typing import Dict, List, Optional
import ray
from pymongo import MongoClient
import os
from ray_cluster_manager import get_ray_manager
from datetime import datetime

# Optional imports for enhanced visualization
try:
    import plotly.graph_objects as go
    import plotly.express as px
    import pandas as pd
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("📊 Plotly not available. Graph visualization will use basic charts.")

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
                    
                    # Show active steps with clear resume functionality
                    if timeline_data.get("active_steps"):
                        st.sidebar.markdown("**🟢 Active Timeline:**")
                        st.sidebar.markdown("*Click 'Resume' to go back to any step*")
                        
                        for step in timeline_data["active_steps"]:
                            step_num = step["step"]
                            action = step["action"].replace("_", " ").title()
                            has_result = step["has_result"]
                            version = step.get("version", 1)
                            user_input = step.get('user_input', 'N/A')
                            
                            # Create meaningful action descriptions
                            action_map = {
                                'Perform Internet Search': '🔍 Web Search',
                                'Perform Github Search': '📂 GitHub Search', 
                                'Perform Atlassian Search': '📋 Atlassian Search',
                                'Generate General Ai Response': '🤖 AI Response',
                                'Search Knowledge Base': '📚 Knowledge Base',
                                'Search Sqlite': '🗄️ Database Search',
                                'Perform Google Maps Search': '🗺️ Maps Search'
                            }
                            
                            action_display = action_map.get(action, action)
                            status_icon = "✅" if has_result else "⏳"
                            
                            # Make the entire step clickable
                            is_selected = st.session_state.get('selected_step_for_history') == step_num
                            button_type = "primary" if is_selected else "secondary"
                            
                            if st.sidebar.button(
                                f"**Step {step_num}:** {action_display} {status_icon}\n*\"{user_input[:40]}{'...' if len(user_input) > 40 else ''}\"*",
                                key=f"sidebar_step_{step_num}",
                                help=f"Click to view conversation history up to step {step_num}",
                                use_container_width=True,
                                type=button_type
                            ):
                                st.session_state.selected_step_for_history = step_num
                                st.rerun()
                            

                            
                            st.sidebar.markdown("---")
                    
                    # Show removed steps in a more compact way
                    if timeline_data.get("removed_steps"):
                        with st.sidebar.expander(f"🗑️ Removed Steps ({len(timeline_data['removed_steps'])})", expanded=False):
                            for step in timeline_data["removed_steps"]:
                                step_num = step["step"]
                                action = step["action"].replace("_", " ").title()
                                version = step.get("version", 1)
                                removed_reason = step.get("removed_reason", "Unknown")
                                
                                # More compact display for removed steps
                                st.write(f"**Step {step_num}.{version}:** {action}")
                                st.caption(f"🗑️ {removed_reason}")
                                if step.get('removed_at'):
                                    st.caption(f"⏰ {step['removed_at'][-8:]}")
                                st.markdown("---")
                    
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
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["💬 Chat", "📊 Conversation Graph"])
    
    with tab1:
        # Check if user selected a specific step to view history from
        selected_step = st.session_state.get('selected_step_for_history')
        
        if selected_step:
            # Show conversation history from selected step with prominent header
            st.markdown("---")
            
            # Create a prominent header section
            header_col1, header_col2, header_col3 = st.columns([1, 2, 1])
            
            with header_col1:
                if st.button("🔙 Back to Latest", key="back_to_full_chat", use_container_width=True):
                    st.session_state.selected_step_for_history = None
                    st.rerun()
            
            with header_col2:
                st.markdown(f"### 📖 Viewing up to Step {selected_step}")
                st.caption("You're viewing conversation history up to this point")
            
            with header_col3:
                # Check if this is not the latest step to show resume option
                try:
                    timeline_response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}/timeline")
                    if timeline_response.status_code == 200:
                        timeline_data = timeline_response.json()["timeline"]
                        active_steps = timeline_data.get("active_steps", [])
                        latest_step = max([s["step"] for s in active_steps]) if active_steps else selected_step
                        
                        if selected_step < latest_step:
                            if st.button(f"🔄 Resume from Step {selected_step}", key="resume_from_chat", type="primary", use_container_width=True):
                                st.session_state.show_resume_confirmation = selected_step
                                st.rerun()
                        else:
                            st.info("📍 Latest Step")
                except:
                    # Fallback: always show resume option
                    if st.button(f"🔄 Resume from Step {selected_step}", key="resume_from_chat", type="primary", use_container_width=True):
                        st.session_state.show_resume_confirmation = selected_step
                        st.rerun()
            
            # Show resume confirmation if requested - make it more prominent
            if st.session_state.get('show_resume_confirmation') == selected_step:
                st.markdown("---")
                
                # Create a warning container with better styling
                with st.container():
                    st.error(f"⚠️ **Resume from Step {selected_step}?**")
                    
                    # Get steps that will be affected
                    try:
                        timeline_response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}/timeline")
                        if timeline_response.status_code == 200:
                            timeline_data = timeline_response.json()["timeline"]
                            active_steps = timeline_data.get("active_steps", [])
                            steps_after = [s for s in active_steps if s["step"] > selected_step]
                            
                            if steps_after:
                                st.markdown(f"**This will remove {len(steps_after)} step(s) that come after Step {selected_step}:**")
                                for step in steps_after:
                                    action = step['action'].replace('_', ' ').title()
                                    st.markdown(f"• **Step {step['step']}:** {action}")
                            else:
                                st.markdown("**No steps will be removed (you're already at the latest step).**")
                    except:
                        st.markdown("**This will remove any steps that come after this point.**")
                    
                    # Confirmation buttons with better layout
                    confirm_col1, confirm_col2, confirm_col3 = st.columns([1, 1, 1])
                    
                    with confirm_col1:
                        if st.button("✅ Yes, Resume Here", key="confirm_resume_chat", type="primary", use_container_width=True):
                            with st.spinner(f"🔄 Resuming from step {selected_step}..."):
                                try:
                                    resume_response = requests.post(f"{BACKEND_URL}/session/{st.session_state.session_id}/resume/{selected_step}")
                                    if resume_response.status_code == 200:
                                        st.success(f"✅ Successfully resumed from step {selected_step}!")
                                        st.balloons()
                                        st.session_state.selected_step_for_history = None
                                        st.session_state.show_resume_confirmation = None
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed to resume from step {selected_step}")
                                except Exception as e:
                                    st.error(f"❌ Error resuming: {str(e)}")
                    
                    with confirm_col3:
                        if st.button("❌ Cancel", key="cancel_resume_chat", use_container_width=True):
                            st.session_state.show_resume_confirmation = None
                            st.rerun()
            
            # Get the conversation history up to the selected step
            try:
                response = requests.get(f"{BACKEND_URL}/session/{st.session_state.session_id}/history/{selected_step}")
                if response.status_code == 200:
                    history_data = response.json()
                    filtered_history = history_data.get("chat_history", [])
                else:
                    # Fallback: show all history
                    filtered_history = session_data.get("chat_history", [])
            except:
                filtered_history = session_data.get("chat_history", [])
            
            st.markdown("---")
        else:
            # Show full conversation history
            filtered_history = session_data.get("chat_history", [])
        
        # Display the chat history (either full or filtered)
        if selected_step:
            st.info(f"📖 Showing conversation up to Step {selected_step}")
        
        for chat_message in filtered_history:
            render_chat_message(chat_message)

        # Get user input (only show if viewing full conversation)
        if not selected_step:
            prompt = st.chat_input("Ask me a question!", key="chat_input")

            if prompt:
                # Process through FastAPI backend
                with st.spinner("Processing your request..."):
                    await process_user_input(prompt)
                st.rerun()
        else:
            st.info("💡 You're viewing historical conversation. Click 'Back to Latest' to continue chatting, or 'Resume' to continue from this point.")
    
    with tab2:
        st.markdown("### 📊 Conversation Visualization")
        st.markdown("Visualize your conversation flow, including timeline branches created by resuming from previous steps.")
        
        if st.session_state.get("session_id"):
            # Sub-tabs for different visualization types
            viz_tab1, viz_tab2 = st.tabs(["🕸️ Network Graph", "📈 Timeline Chart"])
            
            with viz_tab1:
                st.markdown("#### Interactive Network Graph")
                st.markdown("Shows the conversation as a connected graph with nodes representing steps and edges showing flow.")
                create_conversation_graph(st.session_state.session_id)
            
            with viz_tab2:
                st.markdown("#### Timeline Chart")
                st.markdown("Shows the conversation steps over time with active and removed steps.")
                create_timeline_chart(st.session_state.session_id)
        else:
            st.info("Start a conversation to see the visualizations.")


def create_conversation_graph(session_id: str):
    """Create and display an interactive conversation timeline graph"""
    try:
        # Get graph data from backend
        response = requests.get(f"{BACKEND_URL}/session/{session_id}/graph")
        if response.status_code != 200:
            st.error("Failed to load graph data")
            return
        
        graph_data = response.json()
        nodes = graph_data["graph"]["nodes"]
        edges = graph_data["graph"]["edges"]
        stats = graph_data["stats"]
        layout_info = graph_data.get("layout", {})
        
        if not nodes:
            st.info("No conversation steps to visualize yet.")
            return
        
        if not PLOTLY_AVAILABLE:
            # Fallback to simple text-based visualization
            create_simple_graph_visualization(nodes, edges, stats, session_id)
            return
        
        # Layout options with improved default
        layout_type = st.selectbox(
            "Graph Layout",
            ["Smart Timeline", "Hierarchical", "Linear", "Grid"],
            index=0,
            help="Choose the layout algorithm for the graph"
        )
        
        # Calculate positions based on layout type
        pos = {}
        
        if layout_type == "Smart Timeline":
            # Use the improved backend positioning
            for node in nodes:
                pos[node["id"]] = (node.get("x", 0), node.get("y", 0))
        elif layout_type == "Hierarchical":
            # Arrange by step number horizontally, version vertically
            for node in nodes:
                if node["type"] == "start":
                    pos[node["id"]] = (0, 0)
                else:
                    step_num = node.get("step_number", 0)
                    version = node.get("version", 1)
                    pos[node["id"]] = (step_num * 200, (version - 1) * 150)
        elif layout_type == "Linear":
            # Simple linear arrangement
            for i, node in enumerate(nodes):
                pos[node["id"]] = (i * 150, 0)
        else:  # Grid
            # Grid layout
            cols = 4
            for i, node in enumerate(nodes):
                row = i // cols
                col = i % cols
                pos[node["id"]] = (col * 150, row * 100)
        
        # Create Plotly figure with dark theme
        fig = go.Figure()
        
        # Add edges first (so they appear behind nodes)
        for edge in edges:
            source_pos = pos.get(edge["source"], (0, 0))
            target_pos = pos.get(edge["target"], (0, 0))
            
            edge_color = edge.get("color", "#888")
            edge_width = edge.get("width", 1)
            edge_opacity = edge.get("opacity", 0.8)
            edge_type = edge.get("type", "flow")
            
            line_dash = "dash" if edge.get("style") == "dashed" else "solid"
            
            # Add edge type to hover info
            edge_name = ""
            if edge_type == "main_flow":
                edge_name = "Main Timeline"
            elif edge_type == "branch_point":
                edge_name = "Resume Branch"
            elif edge_type == "branch_flow":
                edge_name = "Removed Steps"
            
            fig.add_trace(go.Scatter(
                x=[source_pos[0], target_pos[0]],
                y=[source_pos[1], target_pos[1]],
                mode='lines',
                line=dict(
                    color=edge_color,
                    width=edge_width,
                    dash=line_dash
                ),
                opacity=edge_opacity,
                hoverinfo='text',
                hovertext=edge_name,
                showlegend=False,
                name=edge_name
            ))
        
        # Separate nodes by type for better rendering
        active_nodes = [node for node in nodes if node["type"] == "start" or (node["type"] == "step" and node["is_active"])]
        removed_nodes = [node for node in nodes if node["type"] == "step" and not node["is_active"]]
        
        # Add active nodes (main timeline) with improved styling
        if active_nodes:
            node_x = []
            node_y = []
            node_text = []
            node_colors = []
            node_sizes = []
            node_info = []
            
            for node in active_nodes:
                x, y = pos.get(node["id"], (0, 0))
                node_x.append(x)
                node_y.append(y)
                
                # Create clear, descriptive labels
                if node["type"] == "start":
                    node_text.append("🚀 START")
                    node_colors.append("#00C851")  # Bright green
                    node_sizes.append(35)
                else:
                    # Clear step labels with action description
                    step_label = f"Step {node['step_number']}"
                    action_full = node['action'].replace('_', ' ').title()
                    
                    # Create meaningful action descriptions
                    action_map = {
                        'Perform Internet Search': '🔍 Web Search',
                        'Perform Github Search': '📂 GitHub Search', 
                        'Perform Atlassian Search': '📋 Atlassian Search',
                        'Generate General Ai Response': '🤖 AI Response',
                        'Search Knowledge Base': '📚 Knowledge Base',
                        'Search Sqlite': '🗄️ Database Search',
                        'Perform Google Maps Search': '🗺️ Maps Search'
                    }
                    
                    action_display = action_map.get(action_full, action_full)
                    if len(action_display) > 20:
                        action_display = action_display[:17] + "..."
                    
                    # Show user input preview for context
                    user_preview = node['user_input'][:20] + "..." if len(node['user_input']) > 20 else node['user_input']
                    
                    node_text.append(f"{step_label}\n{action_display}\n\"{user_preview}\"")
                    
                    # Better color scheme with meaning
                    if node['has_result']:
                        node_colors.append("#28A745")  # Green for completed
                    else:
                        node_colors.append("#FFC107")  # Yellow for in progress
                    node_sizes.append(50)
                
                # Create hover info
                if node["type"] == "start":
                    hover_text = "🚀 <b>Start of conversation</b>"
                else:
                    # Get destination display
                    destination = node.get('destination', 'general')
                    destination_display = {
                        'search_internet': '🌐 Internet',
                        'search_github': '📂 GitHub', 
                        'search_atlassian': '📋 Atlassian',
                        'general_ai_response': '🤖 AI Assistant',
                        'search_knowledge_base': '📚 Knowledge Base',
                        'search_sqlite': '🗄️ Database',
                        'search_google_maps': '🗺️ Maps',
                        'email_assistant': '📧 Email',
                        'general': '🤖 AI Assistant',
                        'unknown': '❓ Unknown'
                    }.get(destination, f"📍 {destination.replace('_', ' ').title()}")
                    
                    hover_text = f"""
                    <b>Step {node['step_number']}.{node['version']}</b><br>
                    Action: {action_display}<br>
                    Destination: {destination_display}<br>
                    Status: {'✅ Completed' if node['has_result'] else '⏳ In Progress'}<br>
                    Timestamp: {node['timestamp'][:19]}<br>
                    User Input: "{node['user_input'][:60]}..."<br>
                    <i>Click to view full conversation history from this step</i>
                    """
                
                node_info.append(hover_text)
            
            # Add active nodes trace with better styling
            fig.add_trace(go.Scatter(
                x=node_x,
                y=node_y,
                mode='markers+text',
                marker=dict(
                    size=node_sizes,
                    color=node_colors,
                    line=dict(width=3, color='#2C3E50'),  # Dark border
                    opacity=1.0
                ),
                text=node_text,
                textposition="middle center",
                textfont=dict(
                    size=11, 
                    color="white", 
                    family="Arial Black"
                ),
                hovertemplate='%{customdata}<extra></extra>',
                customdata=node_info,
                showlegend=False,
                name="Active Steps"
            ))
        
        # Add removed nodes (branches) if they exist and user wants to see them
        show_removed = st.checkbox("Show Removed Steps", value=True, 
                                 help="Toggle visibility of removed/inactive steps")
        
        if removed_nodes and show_removed:
            removed_x = []
            removed_y = []
            removed_text = []
            removed_colors = []
            removed_sizes = []
            removed_info = []
            
            for node in removed_nodes:
                x, y = pos.get(node["id"], (0, 0))
                removed_x.append(x)
                removed_y.append(y)
                
                # Shorter labels for removed nodes
                step_label = f"Step {node['step_number']}"
                action_short = node['action'].replace('_', ' ').replace('perform ', '').replace('search ', '').replace('generate ', '').title()
                if len(action_short) > 12:
                    action_short = action_short[:9] + "..."
                removed_text.append(f"{step_label}\n{action_short}\n(Removed)")
                
                removed_colors.append("#6C757D")  # Gray
                removed_sizes.append(30)
                
                # Create hover info for removed nodes
                destination = node.get('destination', 'general')
                destination_display = {
                    'search_internet': '🌐 Internet',
                    'search_github': '📂 GitHub', 
                    'search_atlassian': '📋 Atlassian',
                    'general_ai_response': '🤖 AI Assistant',
                    'search_knowledge_base': '📚 Knowledge Base',
                    'search_sqlite': '🗄️ Database',
                    'search_google_maps': '🗺️ Maps',
                    'email_assistant': '📧 Email',
                    'general': '🤖 AI Assistant',
                    'unknown': '❓ Unknown'
                }.get(destination, f"📍 {destination.replace('_', ' ').title()}")
                
                hover_text = f"""
                <b>Step {node['step_number']}.{node['version']} (Removed)</b><br>
                Action: {node['action'].replace('_', ' ').title()}<br>
                Destination: {destination_display}<br>
                Has Result: {'✅ Yes' if node['has_result'] else '❌ No'}<br>
                Status: 🔴 Removed<br>
                Timestamp: {node['timestamp'][:19]}<br>
                Removed: {node.get('removed_reason', 'Unknown')}<br>
                User Input: {node['user_input'][:50]}...
                """
                
                removed_info.append(hover_text)
            
            # Add removed nodes trace
            fig.add_trace(go.Scatter(
                x=removed_x,
                y=removed_y,
                mode='markers+text',
                marker=dict(
                    size=removed_sizes,
                    color=removed_colors,
                    line=dict(width=2, color='#495057'),  # Darker gray border
                    opacity=0.8
                ),
                text=removed_text,
                textposition="middle center",
                textfont=dict(
                    size=9, 
                    color="white"
                ),
                hovertemplate='%{customdata}<extra></extra>',
                customdata=removed_info,
                showlegend=False,
                name="Removed Steps"
            ))
        
        # Update layout with dark theme and better styling
        fig.update_layout(
            title=dict(
                text=f"📊 Conversation Timeline - Session {session_id[:8]}...",
                x=0.5,
                font=dict(size=20, color="#FFFFFF")
            ),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=60,l=40,r=40,t=80),
            annotations=[
                dict(
                    text=f"📈 {stats['active_steps']} active • 🗑️ {stats['removed_steps']} removed • 🔄 {stats['versions']} versions • 🌿 {stats.get('branches', 0)} branches",
                    showarrow=False,
                    xref="paper", yref="paper",
                    x=0.5, y=-0.08,
                    xanchor="center", yanchor="top",
                    font=dict(size=14, color="#E8E9EA")
                )
            ],
            xaxis=dict(
                showgrid=True, 
                gridcolor='rgba(255,255,255,0.1)',
                gridwidth=1,
                zeroline=False, 
                showticklabels=False,
                title=dict(
                    text="Timeline Progression →",
                    font=dict(color="#E8E9EA", size=12)
                )
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.1)',
                gridwidth=1,
                zeroline=True,
                zerolinecolor='rgba(255,255,255,0.3)',
                zerolinewidth=2,
                showticklabels=False,
                title=dict(
                    text="↑ Active Timeline | Removed Branches ↓",
                    font=dict(color="#E8E9EA", size=12)
                )
            ),
            plot_bgcolor='#1E2329',  # Dark background
            paper_bgcolor='#2C3E50',  # Darker paper background
            height=750,
            font=dict(color="#FFFFFF")
        )
        
        # Add timeline separator line if there are removed steps
        if removed_nodes and show_removed:
            # Add a horizontal line to separate main timeline from branches
            all_x = [pos[node["id"]][0] for node in nodes]
            if all_x:
                min_x, max_x = min(all_x) - 50, max(all_x) + 50
                fig.add_shape(
                    type="line",
                    x0=min_x, y0=-30, x1=max_x, y1=-30,
                    line=dict(color="rgba(255,255,255,0.4)", width=2, dash="dot"),
                )
                fig.add_annotation(
                    x=min_x + 50, y=-30,
                    text="Timeline Separator",
                    showarrow=False,
                    font=dict(size=12, color="#E8E9EA"),
                    yshift=15
                )
        
        # Display the graph
        st.plotly_chart(fig, use_container_width=True)
        
        # Add a note about clicking steps
        st.info("💡 **Tip:** Click on any step in the timeline controls below to view conversation history up to that point.")
        
        # Add enhanced graph statistics and controls
        add_graph_controls_and_stats(nodes, stats, session_id)
        
    except Exception as e:
        st.error(f"Error creating conversation graph: {str(e)}")
        st.exception(e)


def create_simple_graph_visualization(nodes, edges, stats, session_id):
    """Simple text-based graph visualization when Plotly is not available"""
    st.markdown("### 📊 Conversation Flow (Text View)")
    st.markdown("*Enhanced visualization requires Plotly. Showing simplified view.*")
    
    # Show statistics with better styling
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Steps", stats['total_steps'], help="All conversation steps")
    with col2:
        st.metric("Active Steps", stats['active_steps'], help="Current timeline")
    with col3:
        st.metric("Removed Steps", stats['removed_steps'], help="Branched timeline steps")
    with col4:
        st.metric("Timeline Branches", stats.get('branches', 0), help="Resume branches created")
    
    # Show nodes in a structured way with better styling
    st.markdown("### 🔗 Conversation Timeline")
    
    # Separate active and removed nodes
    active_step_nodes = [node for node in nodes if node["type"] == "step" and node["is_active"]]
    removed_step_nodes = [node for node in nodes if node["type"] == "step" and not node["is_active"]]
    
    # Show active timeline
    if active_step_nodes:
        st.markdown("#### 🟢 Active Timeline")
        active_step_nodes.sort(key=lambda x: x.get("step_number", 0))
        
        for i, node in enumerate(active_step_nodes):
            status_icon = "🟢"
            result_icon = "✅" if node["has_result"] else "❌"
            
            # Create a clickable step box
            action_clean = node['action'].replace('_', ' ').title()
            destination = node.get('destination', 'general')
            destination_display = {
                'search_internet': '🌐 Internet',
                'search_github': '📂 GitHub', 
                'search_atlassian': '📋 Atlassian',
                'general_ai_response': '🤖 AI Assistant',
                'search_knowledge_base': '📚 Knowledge Base',
                'search_sqlite': '🗄️ Database',
                'search_google_maps': '🗺️ Maps',
                'email_assistant': '📧 Email',
                'general': '🤖 AI Assistant',
                'unknown': '❓ Unknown'
            }.get(destination, f"📍 {destination.replace('_', ' ').title()}")
            
            # Make the entire step clickable
            is_selected = st.session_state.get('selected_step_for_history') == node['step_number']
            button_type = "primary" if is_selected else "secondary"
            
            if st.button(
                f"{status_icon} **Step {node['step_number']}:** {action_clean} {result_icon}\n"
                f"📍 {destination_display}\n"
                f"🕐 {node['timestamp'][:19]} | 💬 {node['user_input'][:50]}...",
                key=f"simple_step_{node['step_number']}",
                help=f"Click to view conversation history up to step {node['step_number']}",
                use_container_width=True,
                type=button_type
            ):
                st.session_state.selected_step_for_history = node['step_number']
                st.rerun()
            
            # Add connection arrow if not the last step
            if i < len(active_step_nodes) - 1:
                st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;⬇️")
    
    # Show removed branches
    if removed_step_nodes:
        st.markdown("#### 🔴 Removed Timeline Branches")
        
        # Group by branch
        branches = {}
        for node in removed_step_nodes:
            branch_info = node.get('resume_step', 'unknown')
            if branch_info not in branches:
                branches[branch_info] = []
            branches[branch_info].append(node)
        
        for branch_key, branch_nodes in branches.items():
            if isinstance(branch_key, int):
                branch_title = f"Branch from Step {branch_key}"
            else:
                branch_title = "Other Removed Steps"
            
            with st.expander(f"🌿 {branch_title} ({len(branch_nodes)} steps)", expanded=False):
                branch_nodes.sort(key=lambda x: x.get("step_number", 0))
                
                for node in branch_nodes:
                    result_icon = "✅" if node["has_result"] else "❌"
                    action_clean = node['action'].replace('_', ' ').title()
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.markdown(f"**🔴 Step {node['step_number']}.{node['version']}**")
                    with col2:
                        st.markdown(f"**{action_clean}** {result_icon}")
                        st.caption(f"Removed: {node.get('removed_reason', 'Unknown')}")
                        st.caption(f"Input: {node['user_input'][:50]}...")
    
    # Add simple controls
    add_graph_controls_and_stats(nodes, stats, session_id)


def add_graph_controls_and_stats(nodes, stats, session_id):
    """Add common controls and statistics for graph visualization"""
    
    # Add some spacing
    st.markdown("---")
    
    # Enhanced legend with better explanations
    with st.expander("📖 Graph Legend & Guide", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Node Types:**
            - 🟢 **Green**: Start of conversation
            - 🔵 **Blue**: Active step with results
            - 🟠 **Orange**: Active step without results  
            - ⚫ **Gray**: Removed/inactive step
            """)
        
        with col2:
            st.markdown("""
            **Connection Types:**
            - **Thick Blue**: Main timeline flow
            - **Thick Green**: Start connection
            - **Dashed Red**: Resume branch points
            - **Gray Lines**: Removed step connections
            """)
        
        st.markdown("""
        **Layout Guide:**
        - **Top Row (y=0)**: Active conversation timeline
        - **Bottom Rows (y<0)**: Removed steps organized by branch
        - **Left to Right**: Chronological progression of steps
        """)
    
    # Enhanced statistics with better visual presentation
    st.markdown("### 📊 Timeline Statistics")
    
    # Create metrics in a more visually appealing way
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="📝 Total Steps", 
            value=stats['total_steps'], 
            help="All steps ever created in this conversation"
        )
    with col2:
        st.metric(
            label="✅ Active Steps", 
            value=stats['active_steps'], 
            help="Steps currently in the active timeline"
        )
    with col3:
        st.metric(
            label="🗑️ Removed Steps", 
            value=stats['removed_steps'], 
            help="Steps removed due to timeline branching"
        )
    with col4:
        st.metric(
            label="🌿 Timeline Branches", 
            value=stats.get('branches', 0), 
            help="Number of timeline branches created by resume actions"
        )
    
    # Timeline version information with better styling
    if stats.get('versions', 1) > 1:
        st.info(f"🔄 **Timeline Version {stats.get('current_version', 1)}** - This conversation has branched {stats.get('versions', 1)} times due to resume actions.")
    
    # Modern Interactive Controls Section
    st.markdown("### 🎛️ Timeline Controls")
    
    # Create tabs for different control types
    control_tab1, control_tab2, control_tab3 = st.tabs(["🔄 Timeline Management", "📊 Data & Export", "🔍 Step Details"])
    
    with control_tab1:
        st.markdown("#### 🕰️ Timeline Navigation")
        
        # Get active steps for resume functionality
        active_steps = [node for node in nodes if node["type"] == "step" and node["is_active"]]
        
        if active_steps:
            st.markdown("**📍 Click on any step to view conversation history up to that point:**")
            
            # Create a clear, intuitive step list
            for step in sorted(active_steps, key=lambda x: x['step_number']):
                step_num = step['step_number']
                action = step['action'].replace('_', ' ').title()
                user_input = step['user_input']
                has_result = step['has_result']
                timestamp = step['timestamp'][:19].replace('T', ' ')
                
                # Create meaningful action descriptions
                action_map = {
                    'Perform Internet Search': '🔍 Web Search',
                    'Perform Github Search': '📂 GitHub Search', 
                    'Perform Atlassian Search': '📋 Atlassian Search',
                    'Generate General Ai Response': '🤖 AI Response',
                    'Search Knowledge Base': '📚 Knowledge Base',
                    'Search Sqlite': '🗄️ Database Search',
                    'Perform Google Maps Search': '🗺️ Maps Search'
                }
                
                action_display = action_map.get(action, action)
                result_badge = "✅ Completed" if has_result else "⏳ In Progress"
                
                # Get destination information
                destination = step.get('destination', 'general')
                destination_display = {
                    'search_internet': '🌐 Internet',
                    'search_github': '📂 GitHub', 
                    'search_atlassian': '📋 Atlassian',
                    'general_ai_response': '🤖 AI Assistant',
                    'search_knowledge_base': '📚 Knowledge Base',
                    'search_sqlite': '🗄️ Database',
                    'search_google_maps': '🗺️ Maps',
                    'email_assistant': '📧 Email',
                    'general': '🤖 AI Assistant',
                    'unknown': '❓ Unknown'
                }.get(destination, f"📍 {destination.replace('_', ' ').title()}")
                
                # Create a clickable step card
                is_selected = st.session_state.get('selected_step_for_history') == step_num
                button_type = "primary" if is_selected else "secondary"
                
                if st.button(
                    f"**Step {step_num}:** {action_display} → {destination_display}\n"
                    f"{result_badge} | 🕐 {timestamp[-8:]}\n"
                    f"*\"{user_input[:50]}{'...' if len(user_input) > 50 else ''}\"*",
                    key=f"timeline_step_{step_num}",
                    use_container_width=True,
                    help=f"Click to view conversation history up to step {step_num}",
                    type=button_type
                ):
                    st.session_state.selected_step_for_history = step_num
                    st.rerun()
                
                st.markdown("---")
            
            # Show selected step info
            if st.session_state.get('selected_step_for_history'):
                selected_step_num = st.session_state.selected_step_for_history
                st.markdown("---")
                st.success(f"📖 **Currently viewing conversation up to Step {selected_step_num}**")
                st.info("💡 Go to the **Chat** tab to see the conversation history and resume options.")
                
                if st.button(
                    "🔙 Clear Selection",
                    key=f"clear_selection_{selected_step_num}",
                    use_container_width=True
                ):
                    st.session_state.selected_step_for_history = None
                    st.rerun()
        else:
            st.info("🚫 No active steps available for timeline navigation")
        
        # Quick actions
        st.markdown("#### ⚡ Quick Actions")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh Timeline", help="Reload the conversation graph", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🏠 Go to Latest", help="Go back to the most recent step", use_container_width=True):
                if active_steps:
                    latest_step = max(active_steps, key=lambda x: x['step_number'])['step_number']
                    st.session_state.selected_step_for_history = None
                    st.info(f"Viewing latest step: {latest_step}")
                    st.rerun()
                else:
                    st.warning("No active steps to reset to")
    
    with control_tab2:
        st.markdown("#### 📊 Data Export & Analysis")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 View Graph Data", help="Show detailed graph structure", use_container_width=True):
                show_graph_data_modal(nodes, stats, session_id)
        
        with col2:
            if st.button("📋 Export Timeline", help="Export timeline as JSON", use_container_width=True):
                export_timeline_data(nodes, stats, session_id)
    
    with control_tab3:
        show_detailed_step_information(nodes, stats)
    
    # Timeline branch analysis with modern design
    removed_nodes = [node for node in nodes if node["type"] == "step" and not node["is_active"]]
    if removed_nodes:
        st.markdown("### 🌿 Timeline Branches")
        st.markdown("*Explore removed steps organized by timeline branches*")
        
        # Group removed nodes by branch
        branches = {}
        for node in removed_nodes:
            branch_info = node.get('resume_step', 'unknown')
            if branch_info not in branches:
                branches[branch_info] = []
            branches[branch_info].append(node)
        
        # Create columns for branches if there are multiple
        if len(branches) > 1:
            branch_cols = st.columns(min(len(branches), 3))
        else:
            branch_cols = [st.container()]
        
        for i, (branch_key, branch_nodes) in enumerate(branches.items()):
            col_idx = i % 3 if len(branches) > 1 else 0
            
            with branch_cols[col_idx]:
                if isinstance(branch_key, int):
                    branch_title = f"🌿 Branch from Step {branch_key}"
                    branch_desc = f"Created when resuming from step {branch_key}"
                else:
                    branch_title = "🗑️ Other Removed Steps"
                    branch_desc = "Steps removed for other reasons"
                
                with st.expander(f"{branch_title} ({len(branch_nodes)} steps)", expanded=False):
                    st.caption(branch_desc)
                    
                    # Create a mini timeline for this branch
                    for j, node in enumerate(sorted(branch_nodes, key=lambda x: x['step_number'])):
                        result_icon = "✅" if node['has_result'] else "❌"
                        
                        # Create a card-like display for each removed step
                        with st.container():
                            step_col1, step_col2 = st.columns([1, 3])
                            with step_col1:
                                st.markdown(f"**Step {node['step_number']}.{node['version']}**")
                            with step_col2:
                                action_clean = node['action'].replace('_', ' ').title()
                                st.markdown(f"**{action_clean}** {result_icon}")
                                st.caption(f"🗑️ {node.get('removed_reason', 'Unknown')}")
                        
                        # Add visual separator
                        if j < len(branch_nodes) - 1:
                            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;⬇️")


def show_conversation_history_from_step(selected_step: int, active_steps: list, session_id: str):
    """Show conversation history from the selected step with resume option"""
    
    st.markdown("---")
    st.markdown(f"### 📖 Conversation History from Step {selected_step}")
    
    # Get steps from selected step onwards
    steps_from_selected = [s for s in active_steps if s['step_number'] >= selected_step]
    steps_from_selected.sort(key=lambda x: x['step_number'])
    
    if not steps_from_selected:
        st.error("No steps found from the selected point")
        return
    
    # Show the conversation flow from this step
    st.markdown(f"**Showing conversation from Step {selected_step} onwards:**")
    
    for i, step in enumerate(steps_from_selected):
        step_num = step['step_number']
        action = step['action'].replace('_', ' ').title()
        user_input = step['user_input']
        has_result = step['has_result']
        timestamp = step['timestamp'][:19].replace('T', ' ')
        
        # Create meaningful action descriptions
        action_map = {
            'Perform Internet Search': '🔍 Web Search',
            'Perform Github Search': '📂 GitHub Search', 
            'Perform Atlassian Search': '📋 Atlassian Search',
            'Generate General Ai Response': '🤖 AI Response',
            'Search Knowledge Base': '📚 Knowledge Base',
            'Search Sqlite': '🗄️ Database Search',
            'Perform Google Maps Search': '🗺️ Maps Search'
        }
        
        action_display = action_map.get(action, action)
        result_icon = "✅" if has_result else "⏳"
        
        # Highlight the selected step
        if step_num == selected_step:
            st.success(f"**👉 Step {step_num} (Selected):** {action_display} {result_icon}")
        else:
            st.info(f"**Step {step_num}:** {action_display} {result_icon}")
        
        # Show user input and any results
        with st.expander(f"Details for Step {step_num}", expanded=(step_num == selected_step)):
            st.markdown(f"**User Input:** *\"{user_input}\"*")
            st.markdown(f"**Action Taken:** {action_display}")
            st.markdown(f"**Status:** {'Completed' if has_result else 'In Progress'}")
            st.markdown(f"**Timestamp:** {timestamp}")
            
            # Try to get and show the actual result if available
            try:
                step_response = requests.get(f"{BACKEND_URL}/session/{session_id}/step/{step_num}")
                if step_response.status_code == 200:
                    step_data = step_response.json()
                    if step_data.get('result'):
                        st.markdown("**Result:**")
                        st.text_area("", value=str(step_data['result'])[:500] + "..." if len(str(step_data['result'])) > 500 else str(step_data['result']), height=100, disabled=True, key=f"result_{step_num}")
                    else:
                        st.markdown("**Result:** *No result available*")
                else:
                    st.markdown("**Result:** *Could not fetch result*")
            except:
                st.markdown("**Result:** *Could not fetch result*")
        
        # Add flow arrow if not the last step
        if i < len(steps_from_selected) - 1:
            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;⬇️")
    
    # Show resume option if not already at the selected step
    steps_after_selected = [s for s in active_steps if s['step_number'] > selected_step]
    
    if steps_after_selected:
        st.markdown("---")
        st.markdown("### 🔄 Resume Option")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.warning(f"**Resume from Step {selected_step}?**")
            st.markdown(f"This will remove **{len(steps_after_selected)} step(s)** that come after Step {selected_step}:")
            
            for step in steps_after_selected:
                action = step['action'].replace('_', ' ').title()
                action_map = {
                    'Perform Internet Search': '🔍 Web Search',
                    'Perform Github Search': '📂 GitHub Search', 
                    'Perform Atlassian Search': '📋 Atlassian Search',
                    'Generate General Ai Response': '🤖 AI Response',
                    'Search Knowledge Base': '📚 Knowledge Base',
                    'Search Sqlite': '🗄️ Database Search',
                    'Perform Google Maps Search': '🗺️ Maps Search'
                }
                action_display = action_map.get(action, action)
                st.markdown(f"• **Step {step['step_number']}:** {action_display}")
        
        with col2:
            st.markdown("**Actions:**")
            
            if st.button(
                f"✅ Resume from Step {selected_step}",
                key=f"main_resume_{selected_step}",
                type="primary",
                use_container_width=True,
                help=f"Resume conversation from step {selected_step}"
            ):
                perform_resume_action(selected_step, session_id)
            
            if st.button(
                "❌ Cancel",
                key=f"main_cancel_{selected_step}",
                use_container_width=True,
                help="Cancel and go back to timeline view"
            ):
                st.session_state.selected_step_for_history = None
                st.rerun()
    else:
        st.info(f"✅ Step {selected_step} is already the latest step. No resume needed.")
        
        if st.button(
            "🔙 Back to Timeline",
            key=f"back_to_timeline_{selected_step}",
            use_container_width=True
        ):
            st.session_state.selected_step_for_history = None
            st.rerun()


def show_resume_confirmation(step_num: int, active_steps: list, session_id: str):
    """Show a clear confirmation dialog for resume action"""
    
    # Find the selected step
    selected_step = next((s for s in active_steps if s['step_number'] == step_num), None)
    if not selected_step:
        return
    
    # Show what will happen
    steps_after = [s for s in active_steps if s['step_number'] > step_num]
    
    # Create a warning box
    if steps_after:
        st.warning(f"⚠️ **Warning:** Resuming from Step {step_num} will remove {len(steps_after)} step(s) that come after it.")
        
        # Show which steps will be removed
        st.markdown("**Steps that will be removed:**")
        for step in steps_after:
            action = step['action'].replace('_', ' ').title()
            st.markdown(f"• **Step {step['step_number']}:** {action}")
    else:
        st.info("ℹ️ You're already at the latest step. No steps will be removed.")
    
    # Confirmation buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button(
            f"✅ Yes, Resume from Step {step_num}", 
            key=f"confirm_yes_{step_num}",
            type="primary",
            use_container_width=True
        ):
            # Clear the confirmation state
            st.session_state[f'confirm_resume_{step_num}'] = False
            perform_resume_action(step_num, session_id)
    
    with col2:
        if st.button(
            "❌ Cancel", 
            key=f"confirm_no_{step_num}",
            use_container_width=True
        ):
            # Clear the confirmation state
            st.session_state[f'confirm_resume_{step_num}'] = False
            st.rerun()


def perform_resume_action(step_num: int, session_id: str):
    """Perform the actual resume action with user feedback"""
    
    with st.spinner(f"🔄 Resuming from step {step_num}..."):
        try:
            resume_response = requests.post(f"{BACKEND_URL}/session/{session_id}/resume/{step_num}")
            if resume_response.status_code == 200:
                st.success(f"✅ Successfully resumed from step {step_num}!")
                st.info("💡 Previous steps have been preserved in timeline branches for reference")
                
                # Show a brief success animation
                progress_bar = st.progress(0)
                for i in range(100):
                    time.sleep(0.01)
                    progress_bar.progress(i + 1)
                
                st.balloons()  # Celebration animation
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ Failed to resume from step {step_num}")
                st.error(f"Server response: {resume_response.status_code}")
        except Exception as e:
            st.error(f"❌ Error during resume operation: {str(e)}")


def show_step_details_modal(step: dict):
    """Show detailed information about a step in a modal-like display"""
    
    with st.expander(f"🔍 Step {step['step_number']} Details", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📋 Basic Information**")
            st.markdown(f"**Step Number:** {step['step_number']}.{step['version']}")
            st.markdown(f"**Action:** {step['action'].replace('_', ' ').title()}")
            st.markdown(f"**Destination:** {step.get('destination', 'N/A').replace('_', ' ').title()}")
            st.markdown(f"**Has Result:** {'✅ Yes' if step['has_result'] else '❌ No'}")
            st.markdown(f"**Status:** {'🟢 Active' if step['is_active'] else '🔴 Removed'}")
        
        with col2:
            st.markdown("**⏰ Timing Information**")
            st.markdown(f"**Timestamp:** {step['timestamp'][:19]}")
            if not step['is_active']:
                st.markdown(f"**Removed At:** {step.get('removed_at', 'Unknown')}")
                st.markdown(f"**Removed Reason:** {step.get('removed_reason', 'Unknown')}")
        
        st.markdown("**💬 User Input**")
        st.text_area("", value=step['user_input'], height=100, disabled=True, key=f"input_{step['step_number']}")


def show_graph_data_modal(nodes: list, stats: dict, session_id: str):
    """Show graph data in a modal-like display"""
    
    with st.expander("📊 Graph Data Structure", expanded=True):
        tab1, tab2, tab3 = st.tabs(["📈 Statistics", "🔗 Nodes", "📋 Raw Data"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.json({
                    "session_id": session_id[:8] + "...",
                    "total_nodes": len(nodes),
                    "statistics": stats
                })
            with col2:
                node_types = {}
                for node in nodes:
                    node_type = f"{node['type']}_{'active' if node.get('is_active', True) else 'removed'}"
                    node_types[node_type] = node_types.get(node_type, 0) + 1
                st.json({"node_breakdown": node_types})
        
        with tab2:
            for node in nodes:
                if node["type"] != "start":
                    status = "🟢 Active" if node["is_active"] else "🔴 Removed"
                    st.markdown(f"**{status} Step {node['step_number']}.{node['version']}:** {node['action'].replace('_', ' ').title()}")
        
        with tab3:
            st.json({
                "session_id": session_id,
                "total_nodes": len(nodes),
                "statistics": stats,
                "sample_node": nodes[0] if nodes else None
            })


def export_timeline_data(nodes: list, stats: dict, session_id: str):
    """Export timeline data as downloadable JSON"""
    
    export_data = {
        "session_id": session_id,
        "export_timestamp": datetime.utcnow().isoformat(),
        "statistics": stats,
        "nodes": nodes
    }
    
    st.download_button(
        label="📥 Download Timeline Data",
        data=json.dumps(export_data, indent=2),
        file_name=f"timeline_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        help="Download complete timeline data as JSON file"
    )


def show_detailed_step_information(nodes: list, stats: dict):
    """Show detailed step information in a modern tabbed interface"""
    
    st.markdown("#### 📋 Step Information")
    
    # Separate active and removed nodes
    active_nodes = [node for node in nodes if node["type"] == "step" and node["is_active"]]
    removed_nodes = [node for node in nodes if node["type"] == "step" and not node["is_active"]]
    
    if not active_nodes and not removed_nodes:
        st.info("No steps to display")
        return
    
    # Create tabs for different views
    if removed_nodes:
        tab1, tab2 = st.tabs([f"🟢 Active Timeline ({len(active_nodes)})", f"🔴 Removed Branches ({len(removed_nodes)})"])
    else:
        tab1 = st.container()
        tab2 = None
    
    with tab1:
        if active_nodes:
            if PLOTLY_AVAILABLE:
                # Create a modern dataframe view
                active_step_data = []
                for node in sorted(active_nodes, key=lambda x: x['step_number']):
                    # Create meaningful action descriptions
                    action_map = {
                        'Perform Internet Search': '🔍 Web Search',
                        'Perform Github Search': '📂 GitHub Search', 
                        'Perform Atlassian Search': '📋 Atlassian Search',
                        'Generate General Ai Response': '🤖 AI Response',
                        'Search Knowledge Base': '📚 Knowledge Base',
                        'Search Sqlite': '🗄️ Database Search',
                        'Perform Google Maps Search': '🗺️ Maps Search'
                    }
                    action_display = action_map.get(node['action'].replace('_', ' ').title(), node['action'].replace('_', ' ').title())
                    
                    active_step_data.append({
                        "Step": f"{node['step_number']}.{node['version']}",
                        "Action": action_display,
                        "Status": "✅ Completed" if node['has_result'] else "⏳ In Progress",
                        "Time": node['timestamp'][:19],
                        "User Input": node['user_input'][:60] + "..." if len(node['user_input']) > 60 else node['user_input']
                    })
                
                df = pd.DataFrame(active_step_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                # Fallback to card-based view
                for node in sorted(active_nodes, key=lambda x: x['step_number']):
                    with st.container():
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            st.markdown(f"**Step {node['step_number']}.{node['version']}**")
                        with col2:
                            action_clean = node['action'].replace('_', ' ').title()
                            result_status = "✅ Yes" if node['has_result'] else "❌ No"
                            st.markdown(f"**{action_clean}** | Result: {result_status}")
                            st.caption(f"⏰ {node['timestamp'][:19]}")
                            st.caption(f"💬 {node['user_input'][:50]}...")
                        st.markdown("---")
        else:
            st.info("No active steps to display")
    
    if tab2 and removed_nodes:
        with tab2:
            if PLOTLY_AVAILABLE:
                removed_step_data = []
                for node in sorted(removed_nodes, key=lambda x: (x.get('branch_index', 0), x['step_number'])):
                    removed_step_data.append({
                        "Step": f"{node['step_number']}.{node['version']}",
                        "Action": node['action'].replace('_', ' ').title(),
                        "Branch": f"Branch {node.get('branch_index', '?')}" if node.get('branch_index') else "Unknown",
                        "Result": "✅ Yes" if node['has_result'] else "❌ No",
                        "Removed Reason": node.get('removed_reason', 'Unknown'),
                        "Time": node['timestamp'][:19],
                        "Input Preview": node['user_input'][:50] + "..." if len(node['user_input']) > 50 else node['user_input']
                    })
                
                df = pd.DataFrame(removed_step_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                # Fallback to card-based view for removed steps
                for node in sorted(removed_nodes, key=lambda x: (x.get('branch_index', 0), x['step_number'])):
                    with st.container():
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            branch_info = f" (Branch {node.get('branch_index', '?')})" if node.get('branch_index') else ""
                            st.markdown(f"**Step {node['step_number']}.{node['version']}{branch_info}**")
                        with col2:
                            action_clean = node['action'].replace('_', ' ').title()
                            result_status = "✅ Yes" if node['has_result'] else "❌ No"
                            st.markdown(f"**{action_clean}** | Result: {result_status}")
                            st.caption(f"🗑️ {node.get('removed_reason', 'Unknown')}")
                            st.caption(f"💬 {node['user_input'][:50]}...")
                        st.markdown("---")


def create_timeline_chart(session_id: str):
    """Create a timeline chart showing conversation flow"""
    try:
        # Get timeline data
        response = requests.get(f"{BACKEND_URL}/session/{session_id}/timeline")
        if response.status_code != 200:
            st.error("Failed to load timeline data")
            return
        
        timeline_data = response.json()["timeline"]
        active_steps = timeline_data.get("active_steps", [])
        removed_steps = timeline_data.get("removed_steps", [])
        
        if not active_steps and not removed_steps:
            st.info("No conversation steps to visualize yet.")
            return
        
        if not PLOTLY_AVAILABLE:
            # Fallback to simple timeline visualization
            create_simple_timeline_visualization(active_steps, removed_steps)
            return
        
        # Prepare data for timeline chart
        all_steps = active_steps + removed_steps
        
        # Create DataFrame for timeline
        timeline_df = []
        for step in all_steps:
            timeline_df.append({
                "Step": f"Step {step['step']}.{step.get('version', 1)}",
                "Action": step['action'].replace('_', ' ').title(),
                "Timestamp": pd.to_datetime(step['timestamp']),
                "Status": "Active" if step in active_steps else "Removed",
                "Has_Result": step.get('has_result', False),  # Use .get() with default
                "Version": step.get('version', 1)
            })
        
        df = pd.DataFrame(timeline_df)
        
        if df.empty:
            st.info("No timeline data available.")
            return
        
        # Create simple scatter plot instead of timeline
        fig = px.scatter(
            df,
            x="Timestamp",
            y="Step",
            color="Status",
            hover_data=["Action", "Version", "Has_Result"],
            title="Conversation Timeline",
            color_discrete_map={
                "Active": "#2196F3",
                "Removed": "#9E9E9E"
            }
        )
        
        fig.update_layout(
            height=400,
            xaxis_title="Time",
            yaxis_title="Conversation Steps",
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Add step flow diagram
        st.markdown("### 📈 Step Flow Diagram")
        
        # Create a simple flow chart using plotly
        step_numbers = [step['step'] for step in active_steps]
        actions = [step['action'].replace('_', ' ').title() for step in active_steps]
        
        if step_numbers:
            flow_fig = go.Figure()
            
            # Add line connecting steps
            flow_fig.add_trace(go.Scatter(
                x=step_numbers,
                y=[1] * len(step_numbers),
                mode='lines+markers+text',
                text=actions,
                textposition="top center",
                marker=dict(size=15, color='#2196F3'),
                line=dict(color='#2196F3', width=3),
                name="Active Flow"
            ))
            
            # Add removed steps if any
            removed_step_numbers = [step['step'] for step in removed_steps]
            removed_actions = [step['action'].replace('_', ' ').title() for step in removed_steps]
            
            if removed_step_numbers:
                flow_fig.add_trace(go.Scatter(
                    x=removed_step_numbers,
                    y=[0.5] * len(removed_step_numbers),
                    mode='markers+text',
                    text=removed_actions,
                    textposition="bottom center",
                    marker=dict(size=10, color='#9E9E9E', symbol='x'),
                    name="Removed Steps"
                ))
            
            flow_fig.update_layout(
                title="Step Flow (Active vs Removed)",
                xaxis_title="Step Number",
                yaxis=dict(showticklabels=False, range=[0, 2]),
                height=300,
                showlegend=True
            )
            
            st.plotly_chart(flow_fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating timeline chart: {str(e)}")


def create_simple_timeline_visualization(active_steps, removed_steps):
    """Simple timeline visualization when Plotly is not available"""
    st.markdown("### 📅 Timeline (Text View)")
    
    # Combine and sort all steps
    all_steps = active_steps + removed_steps
    all_steps.sort(key=lambda x: x['timestamp'])
    
    st.markdown("#### Chronological Order:")
    for step in all_steps:
        status_icon = "🟢" if step in active_steps else "🔴"
        result_icon = "✅" if step.get('has_result', False) else "❌"
        
        timestamp = step['timestamp'][:19].replace('T', ' ')
        action = step['action'].replace('_', ' ').title()
        
        st.write(f"{status_icon} **{timestamp}** - Step {step['step']}.{step.get('version', 1)}: {action} {result_icon}")
    
    # Show flow
    st.markdown("#### Active Flow:")
    active_steps.sort(key=lambda x: x['step'])
    flow_text = " → ".join([f"Step {s['step']}" for s in active_steps])
    st.write(flow_text)
    
    if removed_steps:
        st.markdown("#### Removed Steps:")
        for step in removed_steps:
            st.write(f"🔴 Step {step['step']}.{step.get('version', 1)}: {step['action'].replace('_', ' ').title()}")


if __name__ == "__main__":
    # This remains for Streamlit's async entry point handling
    asyncio.run(main()) 