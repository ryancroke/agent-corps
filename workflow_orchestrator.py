import asyncio
import ray
from typing import Dict, Callable, Optional
from ray_mongodb_system import (
    ActionType, StateManager, ConversationState,
    get_user_input_task, route_request_task, perform_internet_search_task,
    perform_github_search_task, search_sqlite_task, perform_atlassian_search_task,
    search_knowledge_base_task, generate_general_ai_response_task, prompt_for_more_task,
    perform_google_maps_search_task, get_email_data_task, create_reply_email_task,
    finalize_email_response_task, generate_final_response_task, present_response_task
)

class WorkflowOrchestrator:
    """
    Orchestrates the execution of Ray tasks based on state transitions,
    replacing the Burr graph system with MongoDB state management.
    """
    
    def __init__(self):
        self.state_manager = StateManager()
        
        # Map action types to their corresponding Ray tasks
        self.task_mapping: Dict[str, Callable] = {
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
            ActionType.PROMPT_FOR_MORE.value: ActionType.GET_USER_INPUT.value,
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
    
    async def execute_action(self, session_id: str, action_type: str, **kwargs) -> str:
        """
        Execute a specific action using Ray tasks.
        
        Args:
            session_id: The conversation session ID
            action_type: The type of action to execute
            **kwargs: Additional arguments for the action
            
        Returns:
            The session ID after execution
        """
        if action_type not in self.task_mapping:
            raise ValueError(f"Unknown action type: {action_type}")
        
        task_func = self.task_mapping[action_type]
        
        # Special handling for get_user_input which needs additional parameters
        if action_type == ActionType.GET_USER_INPUT.value:
            user_input = kwargs.get('user_input')
            if not user_input:
                raise ValueError("user_input is required for GET_USER_INPUT action")
            result = task_func.remote(session_id, user_input)
        else:
            result = task_func.remote(session_id)
        
        return ray.get(result)
    
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
        Run the complete workflow for a conversation turn.
        
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

# Convenience functions for easy usage
async def start_conversation(user_input: str) -> tuple[str, ConversationState]:
    """
    Start a new conversation.
    
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
    Continue an existing conversation.
    
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