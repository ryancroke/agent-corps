#!/usr/bin/env python3
"""
Simple launcher for the Ray + MongoDB Streamlit application.
Matches the design philosophy of simple_stremlit_MCP.py
"""

import os
import sys
import subprocess
from pathlib import Path

def setup_environment():
    """Basic environment setup"""
    # Load .env file if it exists
    env_file = Path('.env')
    if env_file.exists():
        try:
            from dotenv import load_dotenv
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

def main():
    """Main function - now launches the full FastAPI + Streamlit stack"""
    print("=" * 60)
    print("🤖 MCP AI Assistant - Ray + MongoDB Launcher")
    print("=" * 60)
    print("📝 Note: This now launches the FastAPI + Streamlit stack")
    print("🔄 Redirecting to full stack launcher...")
    print("=" * 60)
    
    # Basic environment setup
    setup_environment()
    
    # Get the directory of this script
    script_dir = Path(__file__).parent
    stack_launcher = script_dir / "run_fastapi_streamlit_stack.py"
    
    if not stack_launcher.exists():
        print(f"❌ Stack launcher not found: {stack_launcher}")
        print("📝 Please ensure run_fastapi_streamlit_stack.py exists")
        sys.exit(1)
    
    # Run the full stack launcher
    try:
        cmd = [sys.executable, str(stack_launcher)]
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("👋 MCP AI Assistant stopped gracefully")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Failed to run stack: {e}")
        print("🔍 Please check your environment setup and dependencies")
        sys.exit(1)

if __name__ == "__main__":
    main() 