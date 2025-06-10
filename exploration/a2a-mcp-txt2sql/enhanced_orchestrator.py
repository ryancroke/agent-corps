"""
Enhanced orchestrator with A2A SQL validation.
"""

import asyncio
from datetime import datetime
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.sql_validation_agent import SQLValidationAgent
from mcp_isolation import MCPIsolationLayer
from mcp_servers.mcp_factory import create_mcp_interface
from data.chroma.create_db import create_chroma_db, add_interaction


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    query_type: str  # "sql", "memory", "direct"
    needs_sql: bool
    needs_memory: bool
    sql_query: str
    memory_query: str
    is_valid: bool
    validation_result: dict
    sql_result: str
    memory_result: str
    final_response: str
    mcp_servers_used: list[str]
    agents_used: list[str]


class EnhancedSQLOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.sqlite_mcp = None
        self.validator = SQLValidationAgent()
        self.chroma_logger = None
        self.chroma_client = None
        self.chroma_collection = None
        self.checkpointer = InMemorySaver()
        self.graph = None

        # NEW: MCP Isolation Layer
        self.mcp_isolation = MCPIsolationLayer()

    async def initialize(self):
        """Initialize all components."""
        # Use factory to create MCP interfaces directly
        self.sqlite_mcp = await create_mcp_interface("sqlite")
        self.chroma_logger = await create_mcp_interface("chroma")
        
        # Initialize direct ChromaDB connection for logging
        self.chroma_client, self.chroma_collection = create_chroma_db()
        
        await self.validator.initialize()

        # Register MCP servers with isolation layer
        self.mcp_isolation.register_server("sqlite", self.sqlite_mcp)
        self.mcp_isolation.register_server("chroma", self.chroma_logger)

        self.graph = self._build_graph()

    def _build_graph(self):
        """Build LangGraph with A2A validation."""
        graph = StateGraph(State)

        graph.add_node("initialize_state", self._initialize_state)
        graph.add_node("contextualize", self._contextualize_query)
        graph.add_node("route", self._route_query)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_sql", self._execute_sql)
        graph.add_node("search_memory", self._search_memory)
        graph.add_node("direct_response", self._direct_response)

        graph.set_entry_point("contextualize")
        graph.add_edge("contextualize", "initialize_state")
        graph.add_edge("initialize_state", "route")

        # 3-way routing logic
        graph.add_conditional_edges(
            "route",
            self._route_decision
        )

        graph.add_edge("generate_sql", "validate_sql")

        # Validation routing
        graph.add_conditional_edges(
            "validate_sql",
            lambda state: "execute_sql" if state["is_valid"] else "direct_response"
        )

        graph.add_edge("execute_sql", END)
        graph.add_edge("search_memory", END)
        graph.add_edge("direct_response", END)

        return graph.compile(checkpointer=self.checkpointer)

    async def _route_query(self, state: State) -> State:
        """Decide query type: SQL, memory search, or direct response."""
        query = state['user_query']
        
        routing_prompt = f"""
        Analyze this user query and determine the best routing:
        
        Query: {query}
        
        Choose ONE of these options:
        - SQL: Query needs database access (artists, albums, tracks, sales data)
        - MEMORY: Query asks about previous conversations, history, or similar interactions
        - DIRECT: General question that needs a direct LLM response
        
        Examples:
        - "How many artists are there?" → SQL
        - "What did we talk about earlier?" → MEMORY  
        - "Show me similar questions I've asked" → MEMORY
        - "What is Python?" → DIRECT
        
        Respond with exactly one word: SQL, MEMORY, or DIRECT
        """
        
        response = await self.llm.ainvoke(routing_prompt)
        route_decision = response.content.strip().upper()
        
        # Set routing flags
        needs_sql = route_decision == "SQL"
        needs_memory = route_decision == "MEMORY"
        query_type = route_decision.lower()
        
        return {
            **state, 
            "needs_sql": needs_sql,
            "needs_memory": needs_memory,
            "query_type": query_type
        }

    def _route_decision(self, state: State) -> str:
        """Route based on query type."""
        if state["needs_sql"]:
            return "generate_sql"
        elif state["needs_memory"]:
            return "search_memory"
        else:
            return "direct_response"


    async def _contextualize_query(self, state: State) -> State:
        """Rewrite the user's query using the message history from the state."""
        # The last message is the current user query
        user_query = state["messages"][-1].content

        # If it's the start of a conversation, no context needed
        if len(state["messages"]) <= 1:
            return {"user_query": user_query}

        context_prompt = f"""Based on the chat history, rewrite the following user query to be a standalone question.

        History:
        {state['messages']}

        User Query: {user_query}

        Standalone Query:"""

        response = await self.llm.ainvoke(context_prompt)
        rewritten_query = response.content.strip()

        return {"user_query": rewritten_query}

    async def _generate_sql(self, state: State) -> State:
        """Generate SQL query."""
        prompt = f"""Convert to SQL for Chinook music database: {state['user_query']}

Return ONLY the SQL query with no formatting, no code blocks, no explanation.
Example: SELECT COUNT(*) FROM Artist"""

        response = await self.llm.ainvoke(prompt)
        sql_query = response.content.strip()

        # Clean up any markdown formatting
        if sql_query.startswith("```"):
            lines = sql_query.split("\n")
            sql_query = "\n".join(line for line in lines if not line.startswith("```") and line.strip())
            sql_query = sql_query.strip()

        agents_used = state.get("agents_used", []) + ["sql_generator_llm"]

        return {**state, "sql_query": sql_query, "agents_used": agents_used}

    async def _validate_sql(self, state: State) -> State:
        """Validate SQL using A2A agent."""
        # Create A2A message
        a2a_message = {
            "task": {
                "skill": "validate_sql",
                "parameters": {
                    "sql": state["sql_query"]
                }
            }
        }

        # Send to validation agent
        result = await self.validator.process_a2a_message(a2a_message)

        if result["status"] == "completed":
            validation_result = result["artifacts"][0]
            is_valid = validation_result["is_valid"] and validation_result["safe"]
        else:
            validation_result = {"is_valid": False, "issues": ["Validation failed"], "safe": False}
            is_valid = False

        agents_used = state.get("agents_used", []) + ["sql_validation_agent"]
        mcp_servers_used = state.get("mcp_servers_used", []) + ["python_repl_mcp"]

        return {
        **state,
        "is_valid": is_valid,
        "validation_result": validation_result,
        "agents_used": agents_used,
        "mcp_servers_used": mcp_servers_used
        }

    async def _execute_sql(self, state: State) -> State:
        """Execute validated SQL."""
        # Check connection health before executing
        is_healthy = await self.sqlite_mcp.health_check()
        if not is_healthy:
            return {
                **state,
                "sql_result": "MCP connection failed health check",
                "final_response": "Database connection error - please try again",
                "mcp_servers_used": state.get("mcp_servers_used", []) + ["sqlite_mcp_failed"]
            }

        try:
            # Use factory interface directly - much simpler!
            sql_task = f"Execute this SQL query: {state['sql_query']}"
            result = await self.sqlite_mcp.query(sql_task)

            mcp_servers_used = state.get("mcp_servers_used", []) + ["sqlite_mcp_direct"]

            return {
                **state,
                "sql_result": str(result),
                "final_response": str(result),
                "mcp_servers_used": mcp_servers_used
            }
        except Exception as e:
            print(f"❌ SQL execution failed: {e}")
            return {
                **state,
                "sql_result": f"Execution error: {str(e)}",
                "final_response": f"Database query failed: {str(e)}",
                "mcp_servers_used": state.get("mcp_servers_used", []) + ["sqlite_mcp_error"]
            }

    async def _search_memory(self, state: State) -> State:
        """Search ChromaDB for relevant past interactions using direct factory interface."""
        try:
            # Simple, direct query to ChromaDB MCP
            search_query = f"Search the system_interactions collection for content related to: {state['user_query']}"
            
            # Use factory interface directly - no complex isolation layer
            result = await self.chroma_logger.query(search_query)
            
            mcp_servers_used = state.get("mcp_servers_used", []) + ["chroma_mcp_direct"]
            
            # Format the memory results
            if result and len(str(result).strip()) > 10:  # Basic result check
                memory_response = f"Based on your previous interactions:\n\n{result}"
            else:
                memory_response = "I don't have any relevant previous interactions to reference for this query."
            
            return {
                **state,
                "memory_query": search_query,
                "memory_result": str(result),
                "final_response": memory_response,
                "mcp_servers_used": mcp_servers_used
            }
            
        except Exception as e:
            print(f"❌ ChromaDB direct query failed: {e}")
            return {
                **state,
                "memory_query": f"Search for: {state['user_query']}",
                "memory_result": f"Error: {str(e)}",
                "final_response": "I'm having trouble accessing my memory right now. Please try again.",
                "mcp_servers_used": state.get("mcp_servers_used", []) + ["chroma_mcp_error"]
            }

    async def _direct_response(self, state: State) -> State:
        """Handle non-SQL or invalid SQL."""
        if not state["needs_sql"]:
            response = await self.llm.ainvoke(state['user_query'])
            # Clear any previous SQL-related fields for non-SQL responses
            return {
                **state, 
                "final_response": response.content,
                "sql_query": "",  # Clear previous SQL query
                "sql_result": "",  # Clear previous SQL result
                "mcp_servers_used": state.get("mcp_servers_used", []),  # Keep existing MCP usage
                "agents_used": state.get("agents_used", [])  # Keep existing agent usage
            }
        else:
            # SQL was invalid
            issues = state.get("validation_result", {}).get("issues", ["Unknown validation error"])
            error_msg = f"SQL validation failed: {', '.join(issues)}"
            return {**state, "final_response": error_msg}


    async def _log_interaction(self, final_state: State):
        """Logs the complete interaction details to ChromaDB using the tested add_interaction function."""
        try:
            # Use the working add_interaction function directly
            add_interaction(
                collection=self.chroma_collection,
                user_query=final_state.get("user_query", ""),
                response=final_state.get("final_response", ""),
                mcp_servers=final_state.get("mcp_servers_used", []),
                agents=final_state.get("agents_used", []),
                sql_generated=final_state.get("sql_query"),
                validation_result=final_state.get("validation_result")
            )
            print(f"✓ Logged interaction to ChromaDB using add_interaction")
            
        except Exception as e:
            # Never let logging failures crash the main application
            print(f"⚠️ ChromaDB logging failed: {e}")
            pass

    async def _initialize_state(self, state: State) -> State:
        """
        Initializes custom state fields if they don't exist.
        This is crucial for the first run of a new conversation thread.
        """
        # These are the keys that are not part of the initial 'messages' input
        # but are required by downstream nodes.
        required_keys = {
            "standalone_query": "",
            "query_type": "direct",
            "needs_sql": False,
            "needs_memory": False,
            "sql_query": "",
            "memory_query": "",
            "is_valid": False,
            "validation_result": {},
            "sql_result": "",
            "memory_result": "",
            "final_response": "",
            "mcp_servers_used": [],
            "agents_used": []
        }

        # We can't just return the whole state, we need to return a dict
        # of the keys to update.
        updates = {}
        for key, default_value in required_keys.items():
            if key not in state or state[key] is None:
                updates[key] = default_value

        # Also add the original user query for logging purposes
        updates["user_query"] = state["messages"][-1].content

        return updates

    async def run(self, user_query: str, thread_id: str) -> State:
        """Process query through enhanced workflow."""
        inputs = {"messages": [("user", user_query)]}
        config = {"configurable": {"thread_id": thread_id}}

        try:
            final_state = await self.graph.ainvoke(inputs, config)
            await self._log_interaction(final_state)
            return final_state

        except Exception as e:
            print(f"❌ Enhanced Orchestrator - Run failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def close(self):
        """Clean up resources."""
        if self.sqlite_mcp:
            await self.sqlite_mcp.close()
        if self.chroma_logger:
            await self.chroma_logger.close()


# Test function
async def test():
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()

    # Test valid SQL query
    result = await orchestrator.run("How many artists are in the database?", "test-thread-1")
    print(f"Valid query result: {result.get('final_response', 'No response')[:100]}...")

    # Test dangerous SQL
    result = await orchestrator.run("DROP TABLE Artist", "test-thread-2")
    print(f"Dangerous query result: {result.get('final_response', 'No response')}")

    # Test non-SQL query
    result = await orchestrator.run("What is Python?", "test-thread-3")
    print(f"Non-SQL result: {result.get('final_response', 'No response')[:100]}...")

    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(test())
