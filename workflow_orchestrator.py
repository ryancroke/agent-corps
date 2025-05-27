import asyncio
import ray
from typing import Dict, Callable, Optional, List, Any
from ray_mongodb_system import (
    ActionType, StateManager, ConversationState,
    get_user_input_task, route_request_task, perform_internet_search_task,
    perform_github_search_task, search_sqlite_task, perform_atlassian_search_task,
    search_knowledge_base_task, generate_general_ai_response_task, prompt_for_more_task,
    perform_google_maps_search_task, get_email_data_task, create_reply_email_task,
    finalize_email_response_task, generate_final_response_task, present_response_task
)
import time
from dataclasses import dataclass
from enum import Enum

class WorkerType(Enum):
    """Different types of workers for specialized tasks"""
    GENERAL = "general"  # Can handle any task
    SEARCH = "search"    # Specialized for search operations
    AI = "ai"           # Specialized for AI/LLM operations
    EMAIL = "email"     # Specialized for email operations

@dataclass
class TaskRequest:
    """Represents a task request to be executed by workers"""
    session_id: str
    action_type: str
    priority: int = 1  # Higher number = higher priority
    worker_type: WorkerType = WorkerType.GENERAL
    kwargs: Dict[str, Any] = None
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.kwargs is None:
            self.kwargs = {}

@ray.remote
class WorkerPool:
    """
    A Ray actor that manages a pool of workers for executing tasks.
    This provides better resource management and task distribution.
    """
    
    def __init__(self, worker_type: WorkerType = WorkerType.GENERAL, max_concurrent_tasks: int = 4):
        self.worker_type = worker_type
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_tasks = 0
        self.task_queue = []
        self.worker_id = f"{worker_type.value}-{ray.get_runtime_context().get_worker_id()}"
        
        # Map action types to their corresponding functions
        self.task_mapping = {
            ActionType.GET_USER_INPUT.value: get_user_input_task,
            ActionType.ROUTE_REQUEST.value: route_request_task,
            ActionType.PERFORM_INTERNET_SEARCH.value: perform_internet_search_task,
            ActionType.PERFORM_GITHUB_SEARCH.value: perform_github_search_task,
            ActionType.SEARCH_SQLITE.value: search_sqlite_task,
            ActionType.PERFORM_ATLASSIAN_SEARCH.value: perform_atlassian_search_task,
            ActionType.SEARCH_KNOWLEDGE_BASE.value: search_knowledge_base_task,
            ActionType.GENERATE_GENERAL_AI_RESPONSE.value: generate_general_ai_response_task,
            ActionType.PROMPT_FOR_MORE.value: prompt_for_more_task,
            ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value: perform_google_maps_search_task,
            ActionType.GET_EMAIL_DATA.value: get_email_data_task,
            ActionType.CREATE_REPLY_EMAIL.value: create_reply_email_task,
            ActionType.FINALIZE_EMAIL_RESPONSE.value: finalize_email_response_task,
            ActionType.GENERATE_FINAL_RESPONSE.value: generate_final_response_task,
            ActionType.PRESENT_RESPONSE.value: present_response_task,
        }
        
        print(f"Worker pool initialized: {self.worker_id} (type: {worker_type.value})")
    
    def can_handle_task(self, task_request: TaskRequest) -> bool:
        """Check if this worker can handle the given task"""
        if self.current_tasks >= self.max_concurrent_tasks:
            return False
        
        # Check if worker type matches or if it's a general worker
        if self.worker_type == WorkerType.GENERAL:
            return True
        
        # Specialized worker type matching
        action_to_worker_type = {
            ActionType.PERFORM_INTERNET_SEARCH.value: WorkerType.SEARCH,
            ActionType.PERFORM_GITHUB_SEARCH.value: WorkerType.SEARCH,
            ActionType.SEARCH_SQLITE.value: WorkerType.SEARCH,
            ActionType.PERFORM_ATLASSIAN_SEARCH.value: WorkerType.SEARCH,
            ActionType.SEARCH_KNOWLEDGE_BASE.value: WorkerType.SEARCH,
            ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value: WorkerType.SEARCH,
            ActionType.GENERATE_GENERAL_AI_RESPONSE.value: WorkerType.AI,
            ActionType.ROUTE_REQUEST.value: WorkerType.AI,
            ActionType.GET_EMAIL_DATA.value: WorkerType.EMAIL,
            ActionType.CREATE_REPLY_EMAIL.value: WorkerType.EMAIL,
            ActionType.FINALIZE_EMAIL_RESPONSE.value: WorkerType.EMAIL,
        }
        
        required_type = action_to_worker_type.get(task_request.action_type, WorkerType.GENERAL)
        return self.worker_type == required_type
    
    async def execute_task(self, task_request: TaskRequest) -> Any:
        """Execute a single task"""
        if task_request.action_type not in self.task_mapping:
            raise ValueError(f"Unknown action type: {task_request.action_type}")
        
        self.current_tasks += 1
        start_time = time.time()
        
        try:
            print(f"[{self.worker_id}] Starting task: {task_request.action_type} for session {task_request.session_id}")
            
            task_func = self.task_mapping[task_request.action_type]
            
            # Special handling for get_user_input which needs additional parameters
            if task_request.action_type == ActionType.GET_USER_INPUT.value:
                user_input = task_request.kwargs.get('user_input')
                if not user_input:
                    raise ValueError("user_input is required for GET_USER_INPUT action")
                result = await task_func.remote(task_request.session_id, user_input)
            else:
                result = await task_func.remote(task_request.session_id)
            
            execution_time = time.time() - start_time
            print(f"[{self.worker_id}] Completed task: {task_request.action_type} in {execution_time:.2f}s")
            
            # Log task execution for monitoring
            try:
                from task_logger import log_task_execution
                log_task_execution(
                    session_id=task_request.session_id,
                    task_name=task_request.action_type,
                    worker_id=self.worker_id,
                    worker_type=self.worker_type.value
                )
                print(f"[{self.worker_id}] Logged task execution: {task_request.action_type}")
            except ImportError as e:
                # Fallback if logging is not available
                print(f"[{self.worker_id}] Failed to log task execution: {e}")
            except Exception as e:
                print(f"[{self.worker_id}] Error logging task execution: {e}")
            
            return result
            
        finally:
            self.current_tasks -= 1
    
    def get_status(self) -> Dict[str, Any]:
        """Get current worker status"""
        return {
            "worker_id": self.worker_id,
            "worker_type": self.worker_type.value,
            "current_tasks": self.current_tasks,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "queue_size": len(self.task_queue),
            "available": self.current_tasks < self.max_concurrent_tasks
        }

class WorkflowOrchestrator:
    """
    Orchestrates the execution of Ray tasks using a proper worker pool system,
    replacing the Burr graph system with MongoDB state management.
    """
    
    def __init__(self, num_general_workers: int = 2, num_search_workers: int = 2, 
                 num_ai_workers: int = 1, num_email_workers: int = 1):
        self.state_manager = StateManager()
        
        # Initialize worker pools
        self.worker_pools = {
            WorkerType.GENERAL: [WorkerPool.remote(WorkerType.GENERAL) for _ in range(num_general_workers)],
            WorkerType.SEARCH: [WorkerPool.remote(WorkerType.SEARCH) for _ in range(num_search_workers)],
            WorkerType.AI: [WorkerPool.remote(WorkerType.AI) for _ in range(num_ai_workers)],
            WorkerType.EMAIL: [WorkerPool.remote(WorkerType.EMAIL) for _ in range(num_email_workers)]
        }
        
        # Flatten all workers for easier management
        self.all_workers = []
        for worker_list in self.worker_pools.values():
            self.all_workers.extend(worker_list)
        
        print(f"Initialized WorkflowOrchestrator with {len(self.all_workers)} workers")
        
        # Define transition rules (similar to Burr's graph transitions)
        self.transition_rules = {
            ActionType.GET_USER_INPUT.value: ActionType.ROUTE_REQUEST.value,
            ActionType.ROUTE_REQUEST.value: self._determine_next_from_routing,
            ActionType.PERFORM_INTERNET_SEARCH.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.PERFORM_GITHUB_SEARCH.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.SEARCH_SQLITE.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.PERFORM_ATLASSIAN_SEARCH.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.SEARCH_KNOWLEDGE_BASE.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.GENERATE_GENERAL_AI_RESPONSE.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.PROMPT_FOR_MORE.value: ActionType.PRESENT_RESPONSE.value,  # Skip generate_final_response since prompt_for_more sets final_response directly
            ActionType.GET_EMAIL_DATA.value: ActionType.GET_USER_INPUT.value,
            ActionType.CREATE_REPLY_EMAIL.value: ActionType.FINALIZE_EMAIL_RESPONSE.value,
            ActionType.FINALIZE_EMAIL_RESPONSE.value: ActionType.GENERATE_FINAL_RESPONSE.value,
            ActionType.GENERATE_FINAL_RESPONSE.value: ActionType.PRESENT_RESPONSE.value,
            ActionType.PRESENT_RESPONSE.value: ActionType.GET_USER_INPUT.value,
        }
    
    def _determine_next_from_routing(self, state: ConversationState) -> str:
        """
        Determines the next action after routing based on the destination.
        This replaces Burr's conditional transitions.
        """
        destination = state.destination
        
        if destination == "search_internet":
            return ActionType.PERFORM_INTERNET_SEARCH.value
        elif destination == "search_github":
            return ActionType.PERFORM_GITHUB_SEARCH.value
        elif destination == "search_atlassian":
            return ActionType.PERFORM_ATLASSIAN_SEARCH.value
        elif destination == "search_knowledge_base":
            return ActionType.SEARCH_KNOWLEDGE_BASE.value
        elif destination == "general_ai_response":
            return ActionType.GENERATE_GENERAL_AI_RESPONSE.value
        elif destination == "search_google_maps":
            return ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value
        elif destination == "search_sqlite":
            return ActionType.SEARCH_SQLITE.value
        elif destination == "email_assistant":
            return ActionType.GET_EMAIL_DATA.value
        elif destination == "create_reply_email":
            return ActionType.CREATE_REPLY_EMAIL.value
        elif destination == "reset_mode":
            return ActionType.GENERATE_FINAL_RESPONSE.value
        else:  # unknown or default
            return ActionType.PROMPT_FOR_MORE.value
    
    async def _find_available_worker(self, task_request: TaskRequest) -> Optional[Any]:
        """Find an available worker that can handle the task"""
        # First, try to find a specialized worker
        preferred_workers = self.worker_pools.get(task_request.worker_type, [])
        
        # Check specialized workers first
        for worker in preferred_workers:
            status = await worker.get_status.remote()
            if status["available"]:
                can_handle = await worker.can_handle_task.remote(task_request)
                if can_handle:
                    return worker
        
        # If no specialized worker available, try general workers
        if task_request.worker_type != WorkerType.GENERAL:
            for worker in self.worker_pools[WorkerType.GENERAL]:
                status = await worker.get_status.remote()
                if status["available"]:
                    can_handle = await worker.can_handle_task.remote(task_request)
                    if can_handle:
                        return worker
        
        return None
    
    async def execute_action(self, session_id: str, action_type: str, **kwargs) -> Any:
        """
        Execute a specific action using the worker pool.
        
        Args:
            session_id: The conversation session ID
            action_type: The type of action to execute
            **kwargs: Additional arguments for the action
            
        Returns:
            The result from the worker execution
        """
        # Determine worker type based on action
        action_to_worker_type = {
            ActionType.PERFORM_INTERNET_SEARCH.value: WorkerType.SEARCH,
            ActionType.PERFORM_GITHUB_SEARCH.value: WorkerType.SEARCH,
            ActionType.SEARCH_SQLITE.value: WorkerType.SEARCH,
            ActionType.PERFORM_ATLASSIAN_SEARCH.value: WorkerType.SEARCH,
            ActionType.SEARCH_KNOWLEDGE_BASE.value: WorkerType.SEARCH,
            ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value: WorkerType.SEARCH,
            ActionType.GENERATE_GENERAL_AI_RESPONSE.value: WorkerType.AI,
            ActionType.ROUTE_REQUEST.value: WorkerType.AI,
            ActionType.GET_EMAIL_DATA.value: WorkerType.EMAIL,
            ActionType.CREATE_REPLY_EMAIL.value: WorkerType.EMAIL,
            ActionType.FINALIZE_EMAIL_RESPONSE.value: WorkerType.EMAIL,
        }
        
        worker_type = action_to_worker_type.get(action_type, WorkerType.GENERAL)
        
        # Create task request
        task_request = TaskRequest(
            session_id=session_id,
            action_type=action_type,
            worker_type=worker_type,
            kwargs=kwargs
        )
        
        # Find available worker
        worker = await self._find_available_worker(task_request)
        if not worker:
            raise RuntimeError(f"No available worker for task: {action_type}")
        
        # Execute task
        result = await worker.execute_task.remote(task_request)
        return result
    
    def get_next_action(self, session_id: str) -> Optional[str]:
        """
        Determine the next action based on current state and transition rules.
        
        Args:
            session_id: The conversation session ID
            
        Returns:
            The next action type to execute, or None if workflow is complete
        """
        state = self.state_manager.load_state(session_id)
        if not state or not state.last_action:
            return ActionType.GET_USER_INPUT.value
        
        last_action = state.last_action
        
        # Check if next_action is explicitly set in state (overrides rules)
        if state.next_action:
            return state.next_action
        
        # Use transition rules
        if last_action in self.transition_rules:
            next_action_rule = self.transition_rules[last_action]
            
            # If it's a function, call it with state
            if callable(next_action_rule):
                return next_action_rule(state)
            else:
                return next_action_rule
        
        # Default fallback
        return ActionType.GET_USER_INPUT.value
    
    async def run_workflow(self, session_id: str, user_input: str = None, max_steps: int = 10) -> ConversationState:
        """
        Run the complete workflow for a conversation turn using the worker pool.
        
        Args:
            session_id: The conversation session ID
            user_input: User input (required for starting new conversation)
            max_steps: Maximum number of steps to prevent infinite loops
            
        Returns:
            The final conversation state
        """
        current_step = 0
        
        # If user_input is provided, start with GET_USER_INPUT
        if user_input:
            await self.execute_action(session_id, ActionType.GET_USER_INPUT.value, user_input=user_input)
            current_step += 1
        
        # Continue executing actions until we reach a stopping point
        while current_step < max_steps:
            next_action = self.get_next_action(session_id)
            
            if not next_action:
                break
            
            # Stop at GET_USER_INPUT (waiting for user input) unless we just started
            if next_action == ActionType.GET_USER_INPUT.value and current_step > 0:
                break
            
            print(f"Step {current_step}: Executing {next_action}")
            await self.execute_action(session_id, next_action)
            current_step += 1
            
            # Check if we've reached a natural stopping point
            state = self.state_manager.load_state(session_id)
            if state.last_action == ActionType.PRESENT_RESPONSE.value:
                break
        
        # Return final state
        return self.state_manager.load_state(session_id)
    
    async def continue_workflow(self, session_id: str, user_input: str) -> ConversationState:
        """
        Continue an existing workflow with new user input.
        
        Args:
            session_id: The conversation session ID
            user_input: New user input
            
        Returns:
            The final conversation state
        """
        return await self.run_workflow(session_id, user_input)
    
    def create_new_session(self) -> str:
        """
        Create a new conversation session.
        
        Returns:
            The new session ID
        """
        state = self.state_manager.create_new_session()
        return state.session_id
    
    def get_session_state(self, session_id: str) -> Optional[ConversationState]:
        """
        Get the current state of a session.
        
        Args:
            session_id: The conversation session ID
            
        Returns:
            The conversation state or None if not found
        """
        return self.state_manager.load_state(session_id)
    
    def get_chat_history(self, session_id: str) -> list:
        """
        Get the chat history for a session.
        
        Args:
            session_id: The conversation session ID
            
        Returns:
            The chat history as a list of messages
        """
        state = self.state_manager.load_state(session_id)
        return state.chat_history if state else []
    
    async def get_worker_status(self) -> Dict[str, Any]:
        """Get status of all workers in the pool"""
        status = {
            "total_workers": len(self.all_workers),
            "worker_pools": {},
            "workers": []
        }
        
        for worker_type, workers in self.worker_pools.items():
            pool_status = {
                "type": worker_type.value,
                "count": len(workers),
                "available": 0,
                "busy": 0
            }
            
            for worker in workers:
                worker_status = await worker.get_status.remote()
                status["workers"].append(worker_status)
                
                if worker_status["available"]:
                    pool_status["available"] += 1
                else:
                    pool_status["busy"] += 1
            
            status["worker_pools"][worker_type.value] = pool_status
        
        return status

# Convenience functions for easy usage
async def start_conversation(user_input: str) -> tuple[str, ConversationState]:
    """
    Start a new conversation using the worker pool.
    
    Args:
        user_input: The initial user input
        
    Returns:
        Tuple of (session_id, final_state)
    """
    orchestrator = WorkflowOrchestrator()
    session_id = orchestrator.create_new_session()
    final_state = await orchestrator.run_workflow(session_id, user_input)
    return session_id, final_state

async def continue_conversation(session_id: str, user_input: str) -> ConversationState:
    """
    Continue an existing conversation using the worker pool.
    
    Args:
        session_id: The conversation session ID
        user_input: New user input
        
    Returns:
        The final conversation state
    """
    orchestrator = WorkflowOrchestrator()
    return await orchestrator.continue_workflow(session_id, user_input)

def get_conversation_history(session_id: str) -> list:
    """
    Get the conversation history.
    
    Args:
        session_id: The conversation session ID
        
    Returns:
        The chat history as a list of messages
    """
    orchestrator = WorkflowOrchestrator()
    return orchestrator.get_chat_history(session_id) 