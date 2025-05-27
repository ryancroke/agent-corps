import sys
import asyncio
import os
import functools
import openai
from typing import List, Optional, Dict, Tuple, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient
import ray
from pymongo import MongoClient
from datetime import datetime
import uuid
from dataclasses import dataclass, asdict
from enum import Enum

load_dotenv()

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ray will be initialized by the Ray manager when needed

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "mcp_system")
COLLECTION_NAME = "conversation_states"

class ActionType(Enum):
    GET_USER_INPUT = "get_user_input"
    ROUTE_REQUEST = "route_request"
    PERFORM_INTERNET_SEARCH = "perform_internet_search"
    PERFORM_GITHUB_SEARCH = "perform_github_search"
    SEARCH_SQLITE = "search_sqlite"
    PERFORM_ATLASSIAN_SEARCH = "perform_atlassian_search"
    SEARCH_KNOWLEDGE_BASE = "search_knowledge_base"
    GENERATE_GENERAL_AI_RESPONSE = "generate_general_ai_response"
    PROMPT_FOR_MORE = "prompt_for_more"
    GENERATE_FINAL_RESPONSE = "generate_final_response"
    PRESENT_RESPONSE = "present_response"
    PERFORM_GOOGLE_MAPS_SEARCH = "perform_google_maps_search"
    GET_EMAIL_DATA = "get_email_data"
    CREATE_REPLY_EMAIL = "create_reply_email"
    FINALIZE_EMAIL_RESPONSE = "finalize_email_response"

@dataclass
class StateSnapshot:
    """A snapshot of state at a specific step"""
    step: int
    timestamp: str
    user_input: str
    destination: str
    action: str
    previous_state: Dict[str, Any]
    new_state: Dict[str, Any]
    result_stored_in: Optional[str]
    has_result: bool
    # Versioning and observability
    version: int = 1  # Version number for this step
    is_active: bool = True  # Whether this step is in the current timeline
    removed_at: Optional[str] = None  # When this step was removed from timeline
    removed_reason: Optional[str] = None  # Why this step was removed
    # Store the actual results for this step
    internet_search_results: Optional[str] = None
    github_search_results: Optional[str] = None
    general_ai_response: Optional[str] = None
    atlassian_search_results: Optional[str] = None
    knowledge_base_results: Optional[str] = None
    gmaps_results: Optional[str] = None
    sqlite_search_results: Optional[str] = None
    email_response: Optional[str] = None
    final_response: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        return asdict(self)

@dataclass
class ConversationState:
    session_id: str
    user_input: Optional[str] = None
    chat_history: List[Dict[str, str]] = None
    current_mode: str = "general"
    destination: Optional[str] = None
    email_state: Optional[str] = None
    last_action: Optional[str] = None
    next_action: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    # Historical state management
    state_history: List[StateSnapshot] = None
    current_step: int = 0
    current_version: int = 1  # Current version of the conversation
    total_steps_created: int = 0  # Total number of steps ever created (for unique IDs)
    
    # Current active results (from the current or most recent relevant step)
    internet_search_results: Optional[str] = None
    github_search_results: Optional[str] = None
    general_ai_response: Optional[str] = None
    atlassian_search_results: Optional[str] = None
    knowledge_base_results: Optional[str] = None
    gmaps_results: Optional[str] = None
    sqlite_search_results: Optional[str] = None
    email_response: Optional[str] = None
    final_response: Optional[str] = None
    
    def __post_init__(self):
        if self.chat_history is None:
            self.chat_history = []
        if self.state_history is None:
            self.state_history = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def add_state_snapshot(self, user_input: str, destination: str, action: str, 
                          previous_mode: str, new_mode: str, result_key: Optional[str] = None):
        """Add a new state snapshot to history"""
        self.current_step += 1
        self.total_steps_created += 1
        
        snapshot = StateSnapshot(
            step=self.current_step,
            timestamp=datetime.utcnow().isoformat(),
            user_input=user_input,
            destination=destination,
            action=action,
            previous_state={
                "current_mode": previous_mode,
                "email_state": self.email_state,
                "destination": destination
            },
            new_state={
                "current_mode": new_mode,
                "email_state": self.email_state,
                "destination": destination
            },
            result_stored_in=result_key,
            has_result=result_key is not None,
            version=self.current_version,
            is_active=True
        )
        
        # Copy current results to the snapshot
        if result_key:
            setattr(snapshot, result_key, getattr(self, result_key, None))
        
        self.state_history.append(snapshot)
    
    def get_latest_result(self, result_type: str) -> Optional[str]:
        """Get the most recent result of a specific type from history"""
        # First check current state
        current_result = getattr(self, result_type, None)
        if current_result:
            return current_result
        
        # Then check history in reverse order
        for snapshot in reversed(self.state_history):
            if hasattr(snapshot, result_type):
                result = getattr(snapshot, result_type, None)
                if result:
                    return result
        return None
    
    def resume_from_step(self, step_number: int) -> bool:
        """Resume conversation from a specific step with full observability"""
        # Find the target snapshot (must be active)
        target_snapshot = None
        for snapshot in self.state_history:
            if snapshot.step == step_number and snapshot.is_active:
                target_snapshot = snapshot
                break
        
        if not target_snapshot:
            return False
        
        # Mark all steps after the target as removed
        removed_steps = []
        for snapshot in self.state_history:
            if snapshot.step > step_number and snapshot.is_active:
                snapshot.is_active = False
                snapshot.removed_at = datetime.utcnow().isoformat()
                snapshot.removed_reason = f"Resumed from step {step_number}"
                removed_steps.append(snapshot.step)
        
        # Increment version for new timeline
        self.current_version += 1
        
        # Update current state
        self.current_step = step_number
        self.current_mode = target_snapshot.new_state["current_mode"]
        self.email_state = target_snapshot.new_state.get("email_state")
        self.destination = target_snapshot.destination
        
        # Restore the most recent results up to this step
        self._restore_results_up_to_step(step_number)
        
        # Truncate chat history to match the step
        # Each step adds 2 messages (user + assistant)
        self.chat_history = self.chat_history[:step_number * 2]
        
        print(f"Resumed from step {step_number}, removed steps: {removed_steps}, new version: {self.current_version}")
        return True
    
    def _restore_results_up_to_step(self, step_number: int):
        """Restore the most recent results for each type up to the given step (only active steps)"""
        result_types = [
            'internet_search_results', 'github_search_results', 'general_ai_response',
            'atlassian_search_results', 'knowledge_base_results', 'gmaps_results',
            'sqlite_search_results', 'email_response', 'final_response'
        ]
        
        # Clear current results
        for result_type in result_types:
            setattr(self, result_type, None)
        
        # Restore from history up to the target step (only active steps)
        for snapshot in self.state_history:
            if snapshot.step <= step_number and snapshot.is_active:
                for result_type in result_types:
                    if hasattr(snapshot, result_type):
                        result = getattr(snapshot, result_type, None)
                        if result:
                            setattr(self, result_type, result)
    
    def get_active_steps(self) -> List[StateSnapshot]:
        """Get all active steps in the current timeline"""
        return [snapshot for snapshot in self.state_history if snapshot.is_active]
    
    def get_removed_steps(self) -> List[StateSnapshot]:
        """Get all removed steps for observability"""
        return [snapshot for snapshot in self.state_history if not snapshot.is_active]
    
    def get_step_by_number(self, step_number: int, include_removed: bool = False) -> Optional[StateSnapshot]:
        """Get a specific step by number"""
        for snapshot in self.state_history:
            if snapshot.step == step_number:
                if include_removed or snapshot.is_active:
                    return snapshot
        return None
    
    def get_timeline_summary(self) -> Dict[str, Any]:
        """Get a summary of the conversation timeline"""
        active_steps = self.get_active_steps()
        removed_steps = self.get_removed_steps()
        
        return {
            "current_version": self.current_version,
            "current_step": self.current_step,
            "total_steps_created": self.total_steps_created,
            "active_steps_count": len(active_steps),
            "removed_steps_count": len(removed_steps),
            "active_steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "timestamp": s.timestamp,
                    "has_result": s.has_result,
                    "version": s.version
                } for s in active_steps
            ],
            "removed_steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "timestamp": s.timestamp,
                    "removed_at": s.removed_at,
                    "removed_reason": s.removed_reason,
                    "version": s.version
                } for s in removed_steps
            ]
        }

class StateManager:
    def __init__(self, mongo_uri: str = MONGO_URI, db_name: str = DB_NAME):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[COLLECTION_NAME]
        
    def save_state(self, state: ConversationState) -> None:
        """Save conversation state to MongoDB"""
        state.updated_at = datetime.utcnow()
        state_dict = asdict(state)
        
        # Convert state_history to dictionaries for MongoDB storage
        if state_dict.get('state_history'):
            state_dict['state_history'] = [
                snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
                for snapshot in state.state_history
            ]
        
        # Update or insert the state
        self.collection.update_one(
            {"session_id": state.session_id},
            {"$set": state_dict},
            upsert=True
        )
    
    def load_state(self, session_id: str) -> Optional[ConversationState]:
        """Load conversation state from MongoDB"""
        doc = self.collection.find_one({"session_id": session_id})
        if doc:
            # Remove MongoDB's _id field
            doc.pop('_id', None)
            
            # Convert state_history back to StateSnapshot objects
            if doc.get('state_history'):
                doc['state_history'] = [
                    StateSnapshot(**snapshot_dict) if isinstance(snapshot_dict, dict) else snapshot_dict
                    for snapshot_dict in doc['state_history']
                ]
            
            return ConversationState(**doc)
        return None
    
    def create_new_session(self) -> ConversationState:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        state = ConversationState(session_id=session_id)
        self.save_state(state)
        return state

# Configuration constants (same as original)
DESTINATIONS = {
    "search_internet": "internet_search",
    "search_github": "github_search",
    "search_atlassian": "atlassian_search",
    "general_ai_response": "general",
    "email_assistant": "email_assistant",
    "search_google_maps": "google_maps_search",
    "search_knowledge_base": "knowledge_base_search",
    "search_sqlite": "sqlite_search",
    "unknown": "unknown",
    "reset_mode": "general",
}

MCP_CONFIGS = {
    "github": {
        "command": "github-mcp-server/cmd/github-mcp-server/github-mcp-server",
        "args": ["stdio"],
        "working_directory": "github-mcp-server",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PAT}"},
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
    },
    "atlassian": {
        "command": "npx",
        "args": [
            "-y",
            "mcp-remote",
            "https://mcp.atlassian.com/v1/sse",
            "--jira-url",
            "https://haptiq.atlassian.net",
        ]
    },
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-google-maps"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "${GOOGLE_MAPS_API_KEY}"
      }
    },
    "chroma": {
        "command": "uvx",
        "args": [
            "chroma-mcp",
            "--client-type", 
            "persistent",
            "--data-dir", 
            "/Users/ryanhaptiq/Projects/mcp-streamlit-demo/chroma/chroma_db"
        ]
    },
    "sqlite": {
      "command": "npx",
      "args": [
        "-y",
        "@executeautomation/database-server",
        "Chinook_Sqlite.db"
      ]
    }
}

def add_keys_to_config() -> dict:
    config = {}
    config["mcpServers"] = {}
    for key, server_config in MCP_CONFIGS.items():
        config["mcpServers"][key] = server_config.copy()
        if "env" in config["mcpServers"][key]:
            for env_var_key, env_var_placeholder in config["mcpServers"][key][
                "env"
            ].items():
                if env_var_placeholder.startswith(
                    "${"
                ) and env_var_placeholder.endswith("}"):
                    env_var_name = env_var_placeholder[2:-1]
                    config["mcpServers"][key]["env"][env_var_key] = os.getenv(
                        env_var_name
                    )
    return config

def truncate_history(
    history: List[Dict[str, str]], max_turns: int = 5
) -> List[Dict[str, str]]:
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]

@functools.lru_cache
def _get_openai_client():
    openai_client = openai.Client()
    return openai_client

def get_state_manager():
    """Create a new state manager instance for Ray tasks"""
    return StateManager()

def get_llm():
    """Create a new LLM instance for Ray tasks"""
    return ChatOpenAI(model="gpt-4o", temperature=0)

def get_mcp_config():
    """Get MCP configuration for Ray tasks"""
    return add_keys_to_config()

# Ray Tasks (converted from Burr actions)
def get_worker_info():
    """Get current worker information"""
    try:
        import os
        
        # Use process ID as the primary worker identifier
        worker_id = f"pid-{os.getpid()}"
        
        # Get node ID from Ray context
        node_id = 'unknown'
        try:
            runtime_context = ray.get_runtime_context()
            if hasattr(runtime_context, 'get_node_id'):
                node_id = runtime_context.get_node_id()
        except:
            pass
        
        return {
            'worker_id': worker_id,
            'node_id': node_id[:8] if node_id != 'unknown' else 'unknown'
        }
    except Exception as e:
        print(f"Error getting worker info: {e}")
        return {'worker_id': f"pid-{os.getpid()}", 'node_id': 'unknown'}

@ray.remote
def get_user_input_task(session_id: str, user_input: str) -> dict:
    """Ray task for getting user input"""
    worker_info = get_worker_info()
    print(f">>> [Worker {worker_info['worker_id']}] Processing user input: {user_input[:50]}...")
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    if not state:
        state = state_manager.create_new_session()
        state.session_id = session_id
    
    state.user_input = user_input
    state.last_action = ActionType.GET_USER_INPUT.value
    state.next_action = ActionType.ROUTE_REQUEST.value
    
    state_manager.save_state(state)
    return {"session_id": session_id, "worker_info": worker_info}

@ray.remote
def route_request_task(session_id: str) -> dict:
    """Ray task for routing requests"""
    worker_info = get_worker_info()
    print(f">>> [Worker {worker_info['worker_id']}] Routing request...")
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    # Check if we're in the email assistant flow and awaiting data
    if state.current_mode == "email_assistant" and state.email_state == "awaiting_data":
        state.destination = "create_reply_email"
        state.next_action = ActionType.CREATE_REPLY_EMAIL.value
    else:
        # Determine destination using LLM (synchronous version)
        llm = get_llm()
        destination = _determine_destination_sync(state, llm)
        state.destination = destination
        
        # Set next action based on destination
        action_mapping = {
            "search_internet": ActionType.PERFORM_INTERNET_SEARCH.value,
            "search_github": ActionType.PERFORM_GITHUB_SEARCH.value,
            "search_atlassian": ActionType.PERFORM_ATLASSIAN_SEARCH.value,
            "search_knowledge_base": ActionType.SEARCH_KNOWLEDGE_BASE.value,
            "general_ai_response": ActionType.GENERATE_GENERAL_AI_RESPONSE.value,
            "search_google_maps": ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value,
            "search_sqlite": ActionType.SEARCH_SQLITE.value,
            "email_assistant": ActionType.GET_EMAIL_DATA.value,
            "reset_mode": ActionType.GENERATE_FINAL_RESPONSE.value,
            "unknown": ActionType.PROMPT_FOR_MORE.value,
        }
        
        state.next_action = action_mapping.get(destination, ActionType.PROMPT_FOR_MORE.value)
    
    state.last_action = ActionType.ROUTE_REQUEST.value
    state_manager.save_state(state)
    return {"session_id": session_id, "worker_info": worker_info}

async def _determine_destination(state: ConversationState, llm: ChatOpenAI) -> str:
    """Helper function to determine the appropriate destination for user input."""
    prompt = _build_routing_prompt(state.user_input)
    result = await llm.ainvoke(prompt)
    
    raw_destination = result.content.strip().lower()
    destination = _validate_destination(raw_destination)
    
    current_mode = state.current_mode or "general"
    print(f"Current Mode: {current_mode}, Determined Destination: {destination}")
    
    return destination

def _determine_destination_sync(state: ConversationState, llm: ChatOpenAI) -> str:
    """Synchronous helper function to determine the appropriate destination for user input."""
    prompt = _build_routing_prompt(state.user_input)
    result = llm.invoke(prompt)
    
    raw_destination = result.content.strip().lower()
    destination = _validate_destination(raw_destination)
    
    current_mode = state.current_mode or "general"
    print(f"Current Mode: {current_mode}, Determined Destination: {destination}")
    
    return destination

def _build_routing_prompt(user_input: str) -> str:
    """Constructs a clear prompt for the routing LLM."""
    valid_options = [mode for mode in DESTINATIONS.keys() if mode != 'reset_mode']
    options_list = ', '.join(valid_options)
    
    prompt = f"""You are a chatbot classifier. Analyze this user input: "{user_input}"

Your task is to classify this input into exactly ONE of these categories:
{options_list}

Respond with ONLY the category name, nothing else. For example:
- For search queries about the web: "search_internet"
- For questions about coding repositories: "search_github"
- For JIRA or Atlassian questions: "search_atlassian"
- For questions about the internal sqlite DB: "search_sqlite" the name is Chinook_Sqlite.db
- For help with emails or email drafting: "email_assistant"
- For general knowledge questions: "general_ai_response"
- For location or map queries: "search_google_maps"
- For questions about the internal knowledge base. This is a ChromaDB collection and is about our users and their interactions with our product: "search_knowledge_base"
- For queries that don't fit any category: "unknown"

Classification:"""
    
    return prompt

def _validate_destination(raw_destination: str) -> str:
    """Validates and sanitizes the destination returned by the LLM."""
    if raw_destination in DESTINATIONS:
        return raw_destination
    
    print(f"Warning: Invalid destination '{raw_destination}', defaulting to 'unknown'")
    
    for valid_dest in DESTINATIONS.keys():
        if valid_dest in raw_destination:
            print(f"Found partial match: '{valid_dest}'")
            return valid_dest
    
    return "unknown"

@ray.remote
def perform_internet_search_task(session_id: str) -> str:
    """Ray task for internet search"""
    worker_info = get_worker_info()
    print(f">>> [Worker {worker_info['worker_id']}] Performing internet search...")
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    query = state.user_input
    llm = get_llm()
    mcp_config = get_mcp_config()
    previous_mode = state.current_mode
    
    brave_mcp_config = {
        "mcpServers": {"brave-search": mcp_config["mcpServers"]["brave-search"]}
    }
    fresh_client = MCPClient.from_dict(brave_mcp_config)
    fresh_agent = MCPAgent(llm=llm, client=fresh_client, max_steps=12)
    
    # Use asyncio.run for the MCP agent call
    result = asyncio.run(fresh_agent.run(f"Search for information about: {query}"))
    
    # Update state and create snapshot
    state.internet_search_results = result
    state.current_mode = "internet_search"
    state.last_action = ActionType.PERFORM_INTERNET_SEARCH.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_internet",
        action="perform_internet_search",
        previous_mode=previous_mode,
        new_mode="internet_search",
        result_key="internet_search_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def perform_github_search_task(session_id: str) -> str:
    """Ray task for GitHub search"""
    worker_info = get_worker_info()
    print(f">>> [Worker {worker_info['worker_id']}] Searching GitHub...")
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    query = state.user_input
    chat_history = state.chat_history or []
    llm = get_llm()
    mcp_config = get_mcp_config()
    previous_mode = state.current_mode

    truncated_history = truncate_history(chat_history)
    history_string = "\n".join(
        [f"{msg['role'].capitalize()}: {msg['content']}" for msg in truncated_history]
    )

    query_to_send = (
        f"Conversation History:\n{history_string}\nLatest User Input: {query}\nTask:"
    )
    
    github_mcp_config = {"mcpServers": {"github": mcp_config["mcpServers"]["github"]}}
    github_mcp_client = MCPClient.from_dict(github_mcp_config)
    github_mcp_agent = MCPAgent(
        llm=llm, client=github_mcp_client, verbose=True, max_steps=12
    )

    result = asyncio.run(github_mcp_agent.run(query_to_send))
    
    # Update state and create snapshot
    state.github_search_results = result
    state.current_mode = "github_search"
    state.last_action = ActionType.PERFORM_GITHUB_SEARCH.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_github",
        action="perform_github_search",
        previous_mode=previous_mode,
        new_mode="github_search",
        result_key="github_search_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def search_sqlite_task(session_id: str) -> str:
    """Ray task for SQLite search"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Searching sqlite DB...")
    
    query = state.user_input
    chat_history = state.chat_history or []
    llm = get_llm()
    mcp_config = get_mcp_config()

    truncated_history = truncate_history(chat_history)
    history_string = "\n".join(
        [f"{msg['role'].capitalize()}: {msg['content']}" for msg in truncated_history]
    )

    query_to_send = (
        f"Conversation History:\n{history_string}\nLatest User Input: {query}\nTask:"
    )
    
    sqlite_mcp_config = {
        "mcpServers": {"sqlite": mcp_config["mcpServers"]["sqlite"]}
    }
    sqlite_mcp_client = MCPClient.from_dict(sqlite_mcp_config)
    sqlite_mcp_agent = MCPAgent(llm=llm, client=sqlite_mcp_client, max_steps=10)

    result = asyncio.run(sqlite_mcp_agent.run(query_to_send))
    print(f">>> SQLite Search Result: {result}")
    
    # Update state and create snapshot
    state.sqlite_search_results = result
    state.current_mode = "sqlite_search"
    state.last_action = ActionType.SEARCH_SQLITE.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_sqlite",
        action="search_sqlite",
        previous_mode=previous_mode,
        new_mode="sqlite_search",
        result_key="sqlite_search_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def perform_atlassian_search_task(session_id: str) -> str:
    """Ray task for Atlassian search"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Searching JIRA...")
    
    query = state.user_input
    chat_history = state.chat_history or []
    llm = get_llm()
    mcp_config = get_mcp_config()
    previous_mode = state.current_mode

    truncated_history = truncate_history(chat_history)
    history_string = "\n".join(
        [f"{msg['role'].capitalize()}: {msg['content']}" for msg in truncated_history]
    )

    query_to_send = (
        f"Conversation History:\n{history_string}\nLatest User Input: {query}\nTask:"
    )
    
    atlassian_mcp_config = {
        "mcpServers": {"atlassian": mcp_config["mcpServers"]["atlassian"]}
    }
    atlassian_mcp_client = MCPClient.from_dict(atlassian_mcp_config)
    atlassian_mcp_agent = MCPAgent(llm=llm, client=atlassian_mcp_client, max_steps=10)

    result = asyncio.run(atlassian_mcp_agent.run(query_to_send))
    
    # Update state and create snapshot
    state.atlassian_search_results = result
    state.current_mode = "atlassian_search"
    state.last_action = ActionType.PERFORM_ATLASSIAN_SEARCH.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_atlassian",
        action="perform_atlassian_search",
        previous_mode=previous_mode,
        new_mode="atlassian_search",
        result_key="atlassian_search_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def generate_general_ai_response_task(session_id: str) -> dict:
    """Ray task for generating general AI response"""
    worker_info = get_worker_info()
    print(f">>> [Worker {worker_info['worker_id']}] Generating general AI response...")
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    chat_history = state.chat_history or []
    truncated_history = truncate_history(chat_history)
    llm = get_llm()
    previous_mode = state.current_mode

    messages = (
        [
            {"role": "system", "content": "You are a helpful assistant."},
        ]
        + truncated_history
        + [{"role": "user", "content": state.user_input}]
    )

    result = llm.invoke(messages)
    response_content = result.content
    
    # Update state and create snapshot
    state.general_ai_response = response_content
    state.current_mode = "general"
    state.last_action = ActionType.GENERATE_GENERAL_AI_RESPONSE.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=state.user_input,
        destination="general_ai_response",
        action="generate_general_ai_response",
        previous_mode=previous_mode,
        new_mode="general",
        result_key="general_ai_response"
    )
    
    state_manager.save_state(state)
    return {"session_id": session_id, "worker_info": worker_info}

@ray.remote
def prompt_for_more_task(session_id: str) -> str:
    """Ray task for prompting for more information"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Unsure how to handle, prompting for clarification...")
    
    previous_mode = state.current_mode
    response = "I'm not sure how to help with that. Could you please rephrase or provide more detail?"
    print(f"AI: {response}")

    updated_history = (state.chat_history or []) + [
        {"role": "user", "content": state.user_input},
        {"role": "assistant", "content": response},
    ]
    
    # Update state and create snapshot
    state.chat_history = updated_history
    state.current_mode = "general"
    state.last_action = ActionType.PROMPT_FOR_MORE.value
    state.next_action = ActionType.GET_USER_INPUT.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=state.user_input,
        destination="unknown",
        action="prompt_for_more",
        previous_mode=previous_mode,
        new_mode="general",
        result_key=None
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def perform_google_maps_search_task(session_id: str) -> str:
    """Ray task for Google Maps search"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Performing Google Maps search...")
    
    query = state.user_input
    llm = get_llm()
    mcp_config = get_mcp_config()
    previous_mode = state.current_mode
    
    gmaps_mcp_config = {
        "mcpServers": {"google-maps": mcp_config["mcpServers"]["google-maps"]}
    }
    gmaps_mcp_client = MCPClient.from_dict(gmaps_mcp_config)
    gmaps_mcp_agent = MCPAgent(llm=llm, client=gmaps_mcp_client, max_steps=15)

    result = asyncio.run(gmaps_mcp_agent.run(query))
    
    # Update state and create snapshot
    state.gmaps_results = result
    state.current_mode = "google_maps_search"
    state.last_action = ActionType.PERFORM_GOOGLE_MAPS_SEARCH.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_google_maps",
        action="perform_google_maps_search",
        previous_mode=previous_mode,
        new_mode="google_maps_search",
        result_key="gmaps_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def search_knowledge_base_task(session_id: str) -> str:
    """Ray task for knowledge base search"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Searching knowledge base...")
    
    query = state.user_input
    chat_history = state.chat_history or []
    llm = get_llm()
    mcp_config = get_mcp_config()
    previous_mode = state.current_mode
    
    truncated_history = truncate_history(chat_history)
    history_string = "\n".join(
        [f"{msg['role'].capitalize()}: {msg['content']}" for msg in truncated_history]
    )

    query_to_send = (
        f"Task: The user is looking for information from our ChromaDB knowledge base. "
        f"There is a 'user_interactions' collection in ChromaDB. "
        f"Then use the the appropriate chromaDB tool to satisfy the user query: {query}"
    )

    print(f">>> Sending query to ChromaDB agent: {query_to_send}...")
    
    chroma_mcp_config = {
        "mcpServers": {"chroma": mcp_config["mcpServers"]["chroma"]}
    }
    print(f">>> Chroma MCP config: {chroma_mcp_config}")
    chroma_mcp_client = MCPClient.from_dict(chroma_mcp_config)
    chroma_mcp_agent = MCPAgent(llm=llm, client=chroma_mcp_client, max_steps=12)
    
    result = asyncio.run(chroma_mcp_agent.run(query_to_send))
    print(f">>> ChromaDB Search Result: {result}")

    if not result or result.strip() == "":
        result = "Knowledge Base Search Results:\nI searched the knowledge base but couldn't find any information about your query. It's possible that this topic hasn't been discussed before or the knowledge base is still being populated."
    else:
        result = f"Knowledge Base Search Results:\n{result}"
    
    # Update state and create snapshot
    state.knowledge_base_results = result
    state.current_mode = "knowledge_base_search"
    state.last_action = ActionType.SEARCH_KNOWLEDGE_BASE.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    # Add state snapshot
    state.add_state_snapshot(
        user_input=query,
        destination="search_knowledge_base",
        action="search_knowledge_base",
        previous_mode=previous_mode,
        new_mode="knowledge_base_search",
        result_key="knowledge_base_results"
    )
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def get_email_data_task(session_id: str) -> str:
    """Ray task for getting email data"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    response = "To help you draft an email reply, please provide both:\n1. The original email text\n2. Your instructions for how you want to respond\n\nYou can separate them with '---' or clearly label which is which."
    
    updated_history = (state.chat_history or []) + [
        {"role": "user", "content": state.user_input},
        {"role": "assistant", "content": response},
    ]
    
    state.chat_history = updated_history
    state.current_mode = "email_assistant"
    state.email_state = "awaiting_data"
    state.last_action = ActionType.GET_EMAIL_DATA.value
    state.next_action = ActionType.GET_USER_INPUT.value
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def create_reply_email_task(session_id: str) -> str:
    """Ray task for creating reply email"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    if state.email_state != "awaiting_data":
        return session_id
    
    user_input = state.user_input.strip()
    llm = get_llm()
    
    # Process the user input to separate email and instructions
    if "---" in user_input:
        parts = user_input.split("---", 1)
        email_content = parts[0].strip()
        instructions = parts[1].strip()
    else:
        # Send the input to the LLM to intelligently extract email and instructions
        messages = [
            {"role": "system", "content": "You are a helpful assistant that extracts the original email and response instructions from user input."},
            {"role": "user", "content": f"Please identify the original email text and the instructions for how to respond within the following text. Return ONLY a JSON with two keys: 'email' and 'instructions'.\n\n{user_input}"}
        ]
        
        result = llm.invoke(messages)
        try:
            import json
            parsed = json.loads(result.content)
            email_content = parsed.get("email", "")
            instructions = parsed.get("instructions", "")
        except:
            if "email:" in user_input.lower() and "instructions:" in user_input.lower():
                email_start = user_input.lower().find("email:")
                instructions_start = user_input.lower().find("instructions:")
                
                if email_start < instructions_start:
                    email_content = user_input[email_start+6:instructions_start].strip()
                    instructions = user_input[instructions_start+12:].strip()
                else:
                    instructions = user_input[instructions_start+12:email_start].strip()
                    email_content = user_input[email_start+6:].strip()
            else:
                half_point = len(user_input) // 2
                email_content = user_input[:half_point].strip()
                instructions = user_input[half_point:].strip()
    
    print(f"Extracted Email: {email_content[:100]}...")
    print(f"Extracted Instructions: {instructions[:100]}...")
    
    # Generate email reply
    messages = [
        {"role": "system", "content": "You are an email assistant that crafts professional, contextually appropriate responses."},
        {"role": "user", "content": f"Original Email:\n{email_content}\n\nInstructions for Response:\n{instructions}\n\nPlease craft a response email based on these instructions."}
    ]
    
    result = llm.invoke(messages)
    email_response = result.content
    
    response = f"Here's the email response I've created based on your input:\n\n{email_response}"
    
    updated_history = (state.chat_history or []) + [
        {"role": "user", "content": state.user_input},
        {"role": "assistant", "content": response},
    ]
    
    state.email_response = email_response
    state.chat_history = updated_history
    state.email_state = None
    state.last_action = ActionType.CREATE_REPLY_EMAIL.value
    state.next_action = ActionType.FINALIZE_EMAIL_RESPONSE.value
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def finalize_email_response_task(session_id: str) -> str:
    """Ray task for finalizing email response"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    state.final_response = f"Here's the email response I've created based on your input:\n\n{state.email_response}"
    state.current_mode = "general"
    state.email_state = None
    state.last_action = ActionType.FINALIZE_EMAIL_RESPONSE.value
    state.next_action = ActionType.GENERATE_FINAL_RESPONSE.value
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def generate_final_response_task(session_id: str) -> str:
    """Ray task for generating final response"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(">>> Finalizing response...")
    
    final_response_content = "An issue occurred."
    destination = state.destination
    
    # Map destination to current_mode using DESTINATIONS
    new_current_mode = DESTINATIONS.get(destination, "general")
    
    print(f">>> Destination: {destination}")
    print(f">>> Mode: {new_current_mode}")
    
    # Results mapping - links modes to their result variables
    results_mapping = {
        "knowledge_base_search": ("knowledge_base_results", "Knowledge Base Results"),
        "internet_search": ("internet_search_results", "Internet Search Results"),
        "github_search": ("github_search_results", "GitHub Search Results"),
        "atlassian_search": ("atlassian_search_results", "JIRA Search Results"),
        "sqlite_search": ("sqlite_search_results", "SQLite Search Results"),
        "google_maps_search": ("gmaps_results", "Google Maps Search Results"),
        "general": ("general_ai_response", None),
        "email_assistant": ("email_response", "Email Response")
    }
    
    # Get the relevant result for the current mode
    if new_current_mode in results_mapping:
        result_key, prefix = results_mapping[new_current_mode]
        # Use get_latest_result to find the most recent result of this type
        result_content = state.get_latest_result(result_key)
        
        print(f">>> Looking for result in: {result_key}")
        print(f">>> Result content: {result_content}")
        
        if result_content:
            if prefix:
                final_response_content = f"{prefix}:\n{result_content}"
            else:
                final_response_content = result_content
        else:
            print(f">>> No result found for {result_key}, using fallback")
            final_response_content = "I processed your request but didn't get a result. Please try again."
    else:
        print(f">>> Mode {new_current_mode} not found in results_mapping")
        final_response_content = "I processed your request but couldn't determine the appropriate response format."
    
    # Build the chat history update
    user_message = {"role": "user", "content": state.user_input}
    assistant_message = {"role": "assistant", "content": final_response_content}
    updated_history = (state.chat_history or []) + [user_message, assistant_message]
    
    print(f">>> Setting new current mode to: {new_current_mode}")
    
    state.chat_history = updated_history
    state.final_response = final_response_content
    state.current_mode = new_current_mode
    state.last_action = ActionType.GENERATE_FINAL_RESPONSE.value
    state.next_action = ActionType.PRESENT_RESPONSE.value
    
    state_manager.save_state(state)
    return session_id

@ray.remote
def present_response_task(session_id: str) -> str:
    """Ray task for presenting response"""
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    print(f"AI: {state.final_response}")

    # DON'T clear results anymore - preserve them in history
    # Only clear the current user input and update action states
    state.user_input = None
    state.last_action = ActionType.PRESENT_RESPONSE.value
    state.next_action = ActionType.GET_USER_INPUT.value
    
    state_manager.save_state(state)
    return session_id 