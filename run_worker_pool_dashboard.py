#!/usr/bin/env python3
"""
Script to run the Ray Worker Pool Dashboard
Starts both the FastAPI backend and the Streamlit dashboard
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path

def check_port_available(port):
    """Check if a port is available"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False

def start_fastapi_backend():
    """Start the FastAPI backend"""
    print("🚀 Starting FastAPI backend on port 8000...")
    
    if not check_port_available(8000):
        print("⚠️  Port 8000 is already in use. FastAPI backend may already be running.")
        return None
    
    try:
        process = subprocess.Popen([
            sys.executable, "fastapi_ray_backend.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Give it a moment to start
        time.sleep(3)
        
        if process.poll() is None:
            print("✅ FastAPI backend started successfully")
            return process
        else:
            print("❌ Failed to start FastAPI backend")
            return None
    except Exception as e:
        print(f"❌ Error starting FastAPI backend: {e}")
        return None

def start_streamlit_dashboard():
    """Start the Streamlit worker pool dashboard"""
    print("🎨 Starting Streamlit Worker Pool Dashboard on port 8501...")
    
    if not check_port_available(8501):
        print("⚠️  Port 8501 is already in use. Streamlit may already be running.")
        return None
    
    try:
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", 
            "streamlit_worker_pool_dashboard.py",
            "--server.port", "8501",
            "--server.address", "localhost"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Give it a moment to start
        time.sleep(5)
        
        if process.poll() is None:
            print("✅ Streamlit dashboard started successfully")
            print("🌐 Dashboard available at: http://localhost:8501")
            return process
        else:
            print("❌ Failed to start Streamlit dashboard")
            return None
    except Exception as e:
        print(f"❌ Error starting Streamlit dashboard: {e}")
        return None

def main():
    """Main function to orchestrate the startup"""
    print("⚡ Ray Worker Pool Dashboard Launcher")
    print("=" * 50)
    
    # Check if required files exist
    required_files = [
        "fastapi_ray_backend.py",
        "streamlit_worker_pool_dashboard.py",
        "workflow_orchestrator.py",
        "ray_mongodb_system.py"
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing required files: {', '.join(missing_files)}")
        return
    
    processes = []
    
    try:
        # Start FastAPI backend
        fastapi_process = start_fastapi_backend()
        if fastapi_process:
            processes.append(fastapi_process)
        
        # Start Streamlit dashboard
        streamlit_process = start_streamlit_dashboard()
        if streamlit_process:
            processes.append(streamlit_process)
        
        if not processes:
            print("❌ Failed to start any services")
            return
        
        print("\n🎉 Services started successfully!")
        print("📊 Worker Pool Dashboard: http://localhost:8501")
        print("🔧 FastAPI Backend: http://localhost:8000")
        print("📈 Ray Dashboard: http://127.0.0.1:8265")
        print("\n💡 Tips:")
        print("- Use the 'Live Demo' tab to test the worker pool")
        print("- Check 'Worker Details' to see individual worker status")
        print("- Monitor 'Task Logs' for real-time execution tracking")
        print("- Compare 'Performance' metrics before/after improvements")
        print("\nPress Ctrl+C to stop all services...")
        
        # Wait for interrupt
        try:
            while True:
                time.sleep(1)
                # Check if processes are still running
                running_processes = [p for p in processes if p.poll() is None]
                if not running_processes:
                    print("⚠️  All processes have stopped")
                    break
        except KeyboardInterrupt:
            print("\n🛑 Shutting down services...")
    
    finally:
        # Clean up processes
        for process in processes:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                except Exception as e:
                    print(f"Error stopping process: {e}")
        
        print("✅ All services stopped")

if __name__ == "__main__":
    main() 