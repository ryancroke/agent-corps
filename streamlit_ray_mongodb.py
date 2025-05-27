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
                
                # Create shorter, more readable labels
                if node["type"] == "start":
                    node_text.append("🚀 START")
                    node_colors.append("#00C851")  # Bright green
                    node_sizes.append(35)
                else:
                    # Shorter step labels
                    step_label = f"Step {node['step_number']}"
                    action_short = node['action'].replace('_', ' ').replace('perform ', '').replace('search ', '').replace('generate ', '').title()
                    if len(action_short) > 15:
                        action_short = action_short[:12] + "..."
                    node_text.append(f"{step_label}\n{action_short}")
                    
                    # Better color scheme
                    if node['has_result']:
                        node_colors.append("#007BFF")  # Bright blue
                    else:
                        node_colors.append("#FFA500")  # Orange
                    node_sizes.append(40)
                
                # Create hover info
                if node["type"] == "start":
                    hover_text = "🚀 <b>Start of conversation</b>"
                else:
                    hover_text = f"""
                    <b>Step {node['step_number']}.{node['version']}</b><br>
                    Action: {node['action'].replace('_', ' ').title()}<br>
                    Destination: {node.get('destination', 'N/A').replace('_', ' ').title()}<br>
                    Has Result: {'✅ Yes' if node['has_result'] else '❌ No'}<br>
                    Status: 🟢 Active<br>
                    Timestamp: {node['timestamp'][:19]}<br>
                    User Input: {node['user_input'][:50]}...
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
                hover_text = f"""
                <b>Step {node['step_number']}.{node['version']} (Removed)</b><br>
                Action: {node['action'].replace('_', ' ').title()}<br>
                Destination: {node.get('destination', 'N/A').replace('_', ' ').title()}<br>
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
            
            # Create a more visual representation
            col1, col2 = st.columns([1, 4])
            with col1:
                st.markdown(f"**{status_icon} Step {node['step_number']}**")
            with col2:
                action_clean = node['action'].replace('_', ' ').title()
                destination_clean = node.get('destination', 'N/A').replace('_', ' ').title()
                
                st.markdown(f"**{action_clean}** {result_icon}")
                st.caption(f"Destination: {destination_clean}")
                st.caption(f"Time: {node['timestamp'][:19]} | Input: {node['user_input'][:50]}...")
            
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
    
    # Interactive controls with better organization
    st.markdown("### 🎛️ Graph Controls")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**🔄 Actions**")
        if st.button("🔄 Refresh Graph", help="Reload the conversation graph", use_container_width=True):
            st.rerun()
    
    with col2:
        st.markdown("**📊 Data**")
        if st.button("📊 View Raw Data", help="Show the raw graph data structure", use_container_width=True):
            with st.expander("Raw Graph Data", expanded=True):
                st.json({
                    "session_id": session_id,
                    "total_nodes": len(nodes),
                    "node_types": {
                        "start": len([n for n in nodes if n["type"] == "start"]),
                        "active_steps": len([n for n in nodes if n["type"] == "step" and n["is_active"]]),
                        "removed_steps": len([n for n in nodes if n["type"] == "step" and not n["is_active"]])
                    },
                    "statistics": stats
                })
    
    with col3:
        st.markdown("**🔄 Resume**")
        # Quick resume functionality
        active_steps = [node for node in nodes if node["type"] == "step" and node["is_active"]]
        if active_steps:
            step_options = [f"Step {node['step_number']}: {node['action'].replace('_', ' ').title()}" 
                          for node in active_steps]
            selected_step = st.selectbox(
                "Quick Resume",
                ["Select step..."] + step_options,
                help="Resume conversation from any active step (creates a new timeline branch)",
                label_visibility="collapsed"
            )
            
            if selected_step != "Select step...":
                step_num = int(selected_step.split(":")[0].split(" ")[1])
                if st.button(f"🔄 Resume from Step {step_num}", key="quick_resume", use_container_width=True):
                    try:
                        resume_response = requests.post(f"{BACKEND_URL}/session/{session_id}/resume/{step_num}")
                        if resume_response.status_code == 200:
                            st.success(f"✅ Resumed from step {step_num}! New timeline branch created.")
                            st.info("💡 Previous steps after this point moved to removed branch for observability.")
                            time.sleep(1)  # Brief pause to show message
                            st.rerun()
                        else:
                            st.error("❌ Failed to resume from step")
                    except Exception as e:
                        st.error(f"Error resuming: {str(e)}")
        else:
            st.info("No active steps available for resume")
    
    # Timeline branch analysis with better styling
    removed_nodes = [node for node in nodes if node["type"] == "step" and not node["is_active"]]
    if removed_nodes:
        st.markdown("### 🌿 Timeline Branch Analysis")
        
        # Group removed nodes by branch
        branches = {}
        for node in removed_nodes:
            branch_info = node.get('resume_step', 'unknown')
            if branch_info not in branches:
                branches[branch_info] = []
            branches[branch_info].append(node)
        
        for branch_key, branch_nodes in branches.items():
            if isinstance(branch_key, int):
                branch_title = f"🌿 Branch from Step {branch_key}"
                branch_desc = f"Timeline branch created when resuming from step {branch_key}"
            else:
                branch_title = "🗑️ Other Removed Steps"
                branch_desc = "Steps removed for other reasons"
            
            with st.expander(f"{branch_title} ({len(branch_nodes)} steps)", expanded=False):
                st.caption(branch_desc)
                
                # Create a mini timeline for this branch
                for i, node in enumerate(sorted(branch_nodes, key=lambda x: x['step_number'])):
                    result_icon = "✅" if node['has_result'] else "❌"
                    
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.markdown(f"**Step {node['step_number']}.{node['version']}**")
                    with col2:
                        action_clean = node['action'].replace('_', ' ').title()
                        st.markdown(f"**{action_clean}** {result_icon}")
                        st.caption(f"Removed: {node.get('removed_reason', 'Unknown')}")
                        if node.get('removed_at'):
                            st.caption(f"At: {node['removed_at'][:19]}")
                    
                    # Add arrow if not last
                    if i < len(branch_nodes) - 1:
                        st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;⬇️")
    
    # Show detailed step information with better styling
    if st.checkbox("📋 Show Detailed Step Information", value=False):
        st.markdown("### 📋 Detailed Step Information")
        
        # Create tabs for active vs removed steps
        if removed_nodes:
            tab1, tab2 = st.tabs(["🟢 Active Timeline", "🔴 Removed Branches"])
        else:
            tab1 = st.container()
            tab2 = None
        
        with tab1:
            if PLOTLY_AVAILABLE:
                active_step_data = []
                for node in nodes:
                    if node["type"] == "step" and node["is_active"]:
                        active_step_data.append({
                            "Step": f"{node['step_number']}.{node['version']}",
                            "Action": node['action'].replace('_', ' ').title(),
                            "Destination": node.get('destination', 'N/A').replace('_', ' ').title(),
                            "Has Result": "✅ Yes" if node['has_result'] else "❌ No",
                            "Timestamp": node['timestamp'][:19],
                            "User Input": node['user_input'][:50] + "..." if len(node['user_input']) > 50 else node['user_input']
                        })
                
                if active_step_data:
                    df = pd.DataFrame(active_step_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No active steps to display")
            else:
                # Simple text-based table for active steps
                active_nodes = [node for node in nodes if node["type"] == "step" and node["is_active"]]
                if active_nodes:
                    for node in sorted(active_nodes, key=lambda x: x['step_number']):
                        with st.container():
                            col1, col2 = st.columns([1, 4])
                            with col1:
                                st.markdown(f"**Step {node['step_number']}.{node['version']}**")
                            with col2:
                                action_clean = node['action'].replace('_', ' ').title()
                                result_status = "✅ Yes" if node['has_result'] else "❌ No"
                                st.markdown(f"**{action_clean}** | Result: {result_status}")
                                st.caption(f"Time: {node['timestamp'][:19]}")
                                st.caption(f"Input: {node['user_input'][:50]}...")
                            st.markdown("---")
                else:
                    st.info("No active steps to display")
        
        if tab2 and removed_nodes:
            with tab2:
                if PLOTLY_AVAILABLE:
                    removed_step_data = []
                    for node in removed_nodes:
                        removed_step_data.append({
                            "Step": f"{node['step_number']}.{node['version']}",
                            "Action": node['action'].replace('_', ' ').title(),
                            "Destination": node.get('destination', 'N/A').replace('_', ' ').title(),
                            "Has Result": "✅ Yes" if node['has_result'] else "❌ No",
                            "Branch": f"Branch {node.get('branch_index', '?')}" if node.get('branch_index') else "Unknown",
                            "Removed Reason": node.get('removed_reason', 'Unknown'),
                            "Timestamp": node['timestamp'][:19],
                            "User Input": node['user_input'][:50] + "..." if len(node['user_input']) > 50 else node['user_input']
                        })
                    
                    if removed_step_data:
                        df = pd.DataFrame(removed_step_data)
                        st.dataframe(df, use_container_width=True)
                else:
                    # Simple text-based table for removed steps
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
                                st.caption(f"Removed: {node.get('removed_reason', 'Unknown')}")
                                st.caption(f"Input: {node['user_input'][:50]}...")
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