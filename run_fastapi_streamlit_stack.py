#!/usr/bin/env python3
"""
Launcher for FastAPI + Streamlit + Ray + MongoDB Stack
Starts FastAPI backend first, then Streamlit frontend
"""

import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path
from dotenv import load_dotenv

def setup_environment():
    """Basic environment setup"""
    # Load .env file if it exists
    env_file = Path('.env')
    if env_file.exists():
        try:
            load_dotenv()
            print("✅ Loaded .env file")
        except ImportError:
            # Simple manual .env loading
            with open('.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print("✅ Loaded .env file manually")
    
    # Handle MONGODB_CONNECTION_STRING -> MONGO_URI mapping
    if os.getenv('MONGODB_CONNECTION_STRING') and not os.getenv('MONGO_URI'):
        os.environ['MONGO_URI'] = os.getenv('MONGODB_CONNECTION_STRING')
    
    # Set default values
    if not os.getenv('MONGO_URI'):
        os.environ['MONGO_URI'] = 'mongodb://localhost:27017/'
    if not os.getenv('DB_NAME'):
        os.environ['DB_NAME'] = 'mcp_system'

def start_fastapi_backend():
    """Start the FastAPI backend server"""
    script_dir = Path(__file__).parent
    fastapi_file = script_dir / "fastapi_ray_backend.py"
    
    if not fastapi_file.exists():
        print(f"❌ FastAPI backend file not found: {fastapi_file}")
        return None
    
    print("🚀 Starting FastAPI backend on port 8000...")
    
    cmd = [
        sys.executable, "-m", "uvicorn",
        "fastapi_ray_backend:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ]
    
    return subprocess.Popen(cmd)

def start_streamlit_frontend():
    """Start the Streamlit frontend"""
    script_dir = Path(__file__).parent
    streamlit_file = script_dir / "streamlit_ray_mongodb.py"
    
    if not streamlit_file.exists():
        print(f"❌ Streamlit file not found: {streamlit_file}")
        return None
    
    print("🌐 Starting Streamlit frontend on port 8501...")
    
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(streamlit_file),
        "--server.port", "8501",
        "--server.address", "localhost",
        "--browser.gatherUsageStats", "false"
    ]
    
    return subprocess.Popen(cmd)

def wait_for_backend(max_attempts=30):
    """Wait for FastAPI backend to be ready"""
    import requests
    
    for attempt in range(max_attempts):
        try:
            response = requests.get("http://localhost:8000/", timeout=2)
            if response.status_code == 200:
                print("✅ FastAPI backend is ready!")
                return True
        except:
            pass
        
        print(f"⏳ Waiting for backend... ({attempt + 1}/{max_attempts})")
        time.sleep(1)
    
    print("❌ FastAPI backend failed to start")
    return False

def main():
    """Main function to orchestrate the stack startup"""
    print("=" * 70)
    print("🤖 MCP AI Assistant - FastAPI + Streamlit + Ray Stack")
    print("=" * 70)
    
    # Setup environment
    setup_environment()
    
    # Start FastAPI backend
    fastapi_process = start_fastapi_backend()
    if not fastapi_process:
        sys.exit(1)
    
    # Wait for backend to be ready
    if not wait_for_backend():
        fastapi_process.terminate()
        sys.exit(1)
    
    # Start Streamlit frontend
    streamlit_process = start_streamlit_frontend()
    if not streamlit_process:
        fastapi_process.terminate()
        sys.exit(1)
    
    print("=" * 70)
    print("🎉 Stack started successfully!")
    print("🔧 FastAPI Backend: http://localhost:8000")
    print("🌐 Streamlit Frontend: http://localhost:8501")
    print("📱 Features: Ray distributed computing, MongoDB state management")
    print("🔧 MCP Servers: GitHub, Internet Search, Atlassian, Google Maps, SQLite")
    print("=" * 70)
    print("💡 Tip: Use Ctrl+C to stop both services")
    print()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n" + "=" * 70)
        print("🛑 Shutting down services...")
        streamlit_process.terminate()
        fastapi_process.terminate()
        
        # Wait for processes to terminate
        streamlit_process.wait()
        fastapi_process.wait()
        
        print("👋 MCP AI Assistant stack stopped gracefully")
        print("=" * 70)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Wait for both processes
        while True:
            # Check if either process has died
            if fastapi_process.poll() is not None:
                print("❌ FastAPI backend stopped unexpectedly")
                streamlit_process.terminate()
                break
            
            if streamlit_process.poll() is not None:
                print("❌ Streamlit frontend stopped unexpectedly")
                fastapi_process.terminate()
                break
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main() 