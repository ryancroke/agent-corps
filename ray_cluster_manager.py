#!/usr/bin/env python3
"""
Ray Cluster Manager
Handles Ray initialization, cleanup, and signal management
"""

import ray
import os
import signal
import sys
import time
import atexit
from typing import Optional

class RayClusterManager:
    """Manages Ray cluster lifecycle with proper signal handling"""
    
    def __init__(self):
        self.ray_initialized = False
        self.original_sigterm_handler = None
        self.original_sigint_handler = None
        
    def init_ray(self, ignore_reinit_error: bool = True) -> bool:
        """Initialize Ray with proper signal handling"""
        try:
            if ray.is_initialized():
                print("Ray already initialized")
                self.ray_initialized = True
                return True
            
            # Store original signal handlers
            self.original_sigterm_handler = signal.signal(signal.SIGTERM, signal.SIG_DFL)
            self.original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_DFL)
            
            # Initialize Ray with specific configuration
            ray.init(
                ignore_reinit_error=ignore_reinit_error,
                _temp_dir="/tmp/ray",
                logging_level="ERROR",  # Reduce log noise
                log_to_driver=False,
                configure_logging=False,
                runtime_env={"env_vars": {"RAY_DISABLE_IMPORT_WARNING": "1"}}
            )
            
            # Restore original signal handlers after Ray init
            if self.original_sigterm_handler:
                signal.signal(signal.SIGTERM, self.original_sigterm_handler)
            if self.original_sigint_handler:
                signal.signal(signal.SIGINT, self.original_sigint_handler)
            
            self.ray_initialized = True
            print(f"Ray initialized successfully. Dashboard: http://127.0.0.1:8265")
            
            # Register cleanup on exit
            atexit.register(self.cleanup)
            
            return True
            
        except Exception as e:
            print(f"Ray initialization failed: {e}")
            self.ray_initialized = False
            return False
    
    def is_healthy(self) -> bool:
        """Check if Ray cluster is healthy"""
        try:
            if not self.ray_initialized or not ray.is_initialized():
                return False
            
            # Try to get cluster resources as a health check
            resources = ray.cluster_resources()
            return len(resources) > 0
            
        except Exception as e:
            print(f"Ray health check failed: {e}")
            return False
    
    def get_cluster_info(self) -> dict:
        """Get detailed cluster information"""
        try:
            if not self.is_healthy():
                return {"status": False, "error": "Ray not healthy"}
            
            resources = ray.cluster_resources()
            nodes = ray.nodes()
            
            # Get running tasks with error handling
            tasks = []
            try:
                # Try different methods to get task info based on Ray version
                if hasattr(ray.util, 'state') and hasattr(ray.util.state, 'list_tasks'):
                    task_info = ray.util.state.list_tasks(limit=100, detail=True)
                    for task in task_info:
                        if task.get('state') in ['RUNNING', 'PENDING_ARGS_AVAIL', 'PENDING_NODE_ASSIGNMENT']:
                            tasks.append({
                                'task_id': task.get('task_id', 'unknown')[:8],
                                'name': task.get('name', 'unknown'),
                                'state': task.get('state', 'unknown'),
                                'node_id': task.get('node_id', 'unknown')[:8] if task.get('node_id') else 'unknown',
                                'worker_id': task.get('worker_id', 'unknown')[:8] if task.get('worker_id') else 'unknown'
                            })
                else:
                    # Fallback for older Ray versions - just return empty tasks
                    pass
            except Exception as e:
                print(f"Could not get task info: {e}")
            
            return {
                'status': True,
                'resources': resources,
                'nodes': nodes,
                'tasks': tasks,
                'num_cpus': int(resources.get('CPU', 0)),
                'num_nodes': len(nodes),
                'num_workers': sum(1 for node in nodes if node.get('Alive', False))
            }
            
        except Exception as e:
            return {"status": False, "error": str(e)}
    
    def cleanup(self):
        """Clean shutdown of Ray"""
        try:
            if self.ray_initialized and ray.is_initialized():
                print("Shutting down Ray cluster...")
                ray.shutdown()
                self.ray_initialized = False
                print("Ray cluster shutdown complete")
        except Exception as e:
            print(f"Error during Ray cleanup: {e}")
    
    def restart(self) -> bool:
        """Restart Ray cluster"""
        print("Restarting Ray cluster...")
        self.cleanup()
        time.sleep(2)  # Give it time to clean up
        return self.init_ray()

# Global instance
ray_manager = RayClusterManager()

def get_ray_manager() -> RayClusterManager:
    """Get the global Ray manager instance"""
    return ray_manager

def ensure_ray_initialized() -> bool:
    """Ensure Ray is initialized and healthy"""
    manager = get_ray_manager()
    
    if not manager.is_healthy():
        print("Ray not healthy, attempting to initialize...")
        return manager.init_ray()
    
    return True

if __name__ == "__main__":
    # Test the Ray manager
    manager = RayClusterManager()
    
    print("Testing Ray Cluster Manager...")
    success = manager.init_ray()
    print(f"Initialization: {'✅' if success else '❌'}")
    
    if success:
        info = manager.get_cluster_info()
        print(f"Cluster status: {'✅' if info['status'] else '❌'}")
        if info['status']:
            print(f"CPUs: {info['num_cpus']}, Nodes: {info['num_nodes']}, Workers: {info['num_workers']}")
    
    manager.cleanup() 