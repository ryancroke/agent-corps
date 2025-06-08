"""
MCP Isolation Layer - Clean interface between LangGraph and MCP servers.

This module provides a clean, typed interface that isolates MCP servers from
LangGraph state contamination while ensuring proper data types are passed.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MCPQueryContext:
    """Clean, immutable query context for MCP servers."""
    user_query: str
    sql_query: str | None = None
    query_type: str = "sql"  # sql, search, etc.
    database_name: str | None = None

    def __post_init__(self):
        """Validate the query context."""
        if not self.user_query.strip():
            raise ValueError("user_query cannot be empty")
        if self.query_type == "sql" and not self.sql_query:
            raise ValueError("sql_query required when query_type is 'sql'")


@dataclass(frozen=True)
class MCPResponse:
    """Clean, typed response from MCP servers."""
    success: bool
    content: str
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate the response."""
        if not self.success and not self.error_message:
            raise ValueError("error_message required when success=False")


class MCPServer(Protocol):
    """Protocol defining the interface for MCP servers."""

    async def execute_query(self, context: MCPQueryContext) -> MCPResponse:
        """Execute a query with clean context."""
        ...

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        ...


class MCPIsolationLayer:
    """
    Isolation layer that provides clean interfaces to MCP servers.
    
    This layer:
    1. Converts LangGraph state to clean MCPQueryContext
    2. Routes to appropriate MCP servers
    3. Returns clean MCPResponse objects
    4. Prevents state contamination
    """

    def __init__(self):
        self.servers: dict[str, MCPServer] = {}

    def register_server(self, server_type: str, server: MCPServer) -> None:
        """Register an MCP server."""
        self.servers[server_type] = server
        print(f"🔌 Registered MCP server: {server_type}")

    def extract_clean_context(self, langgraph_state: dict[str, Any]) -> MCPQueryContext:
        """
        Extract clean query context from LangGraph state.
        
        This is the critical isolation point - we only extract what's needed
        and ignore all LangGraph orchestration artifacts.
        """
        print("🧹 Extracting clean context from LangGraph state")
        print(f"🔍 Available state keys: {list(langgraph_state.keys())}")

        # Extract only the essential information
        user_query = langgraph_state.get("user_query", "")
        sql_query = langgraph_state.get("sql_query", "")

        # Validate user query exists
        if not user_query:
            raise ValueError("user_query not found in LangGraph state")

        # Create clean context
        context = MCPQueryContext(
            user_query=user_query,
            sql_query=sql_query if sql_query else None,
            query_type="sql" if sql_query else "direct",
            database_name="chinook"
        )

        print("✅ Clean context created:")
        print(f"   User query: '{context.user_query[:50]}...'")
        print(f"   SQL query: '{context.sql_query[:50] if context.sql_query else 'None'}...'")
        print(f"   Query type: {context.query_type}")

        return context

    async def execute_sql_query(self, langgraph_state: dict[str, Any]) -> MCPResponse:
        """
        Execute SQL query through isolated SQLite MCP server.
        
        Args:
            langgraph_state: Full LangGraph state (will be cleaned)
            
        Returns:
            Clean MCPResponse with no state contamination
        """
        print("🎯 MCP Isolation Layer - Executing SQL query")

        # Step 1: Extract clean context
        try:
            context = self.extract_clean_context(langgraph_state)
        except Exception as e:
            print(f"❌ Failed to extract clean context: {e}")
            return MCPResponse(
                success=False,
                content="",
                error_message=f"Context extraction failed: {str(e)}"
            )

        # Step 2: Get SQLite server
        sqlite_server = self.servers.get("sqlite")
        if not sqlite_server:
            print("❌ SQLite MCP server not registered")
            return MCPResponse(
                success=False,
                content="",
                error_message="SQLite MCP server not available"
            )

        # Step 3: Execute with clean context
        try:
            print("🔄 Executing query via isolated SQLite MCP server")

            # Create clean task description from context
            task_description = f"Execute this SQL query: {context.sql_query}"

            # Use the factory-created interface's query method
            result = await sqlite_server.query(task_description)

            # Check for error indicators in the response
            error_indicators = ["error", "failed", "cannot", "unable", "exception", "invalid", "issue", "problem", "try again"]
            result_lower = str(result).lower()
            found_errors = [indicator for indicator in error_indicators if indicator in result_lower]

            if found_errors:
                response = MCPResponse(
                    success=False,
                    content=str(result),
                    error_message=f"Query execution returned error indicators: {found_errors}",
                    metadata={"error_indicators": found_errors}
                )
            else:
                response = MCPResponse(
                    success=True,
                    content=str(result),
                    metadata={
                        "query_executed": context.sql_query,
                        "execution_method": "factory_interface"
                    }
                )

            print(f"✅ SQL execution completed - Success: {response.success}")
            return response

        except Exception as e:
            print(f"❌ SQL execution failed: {e}")
            return MCPResponse(
                success=False,
                content="",
                error_message=f"SQL execution failed: {str(e)}"
            )

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered MCP servers."""
        health_status = {}
        for server_type, server in self.servers.items():
            try:
                health_status[server_type] = await server.health_check()
            except Exception as e:
                print(f"❌ Health check failed for {server_type}: {e}")
                health_status[server_type] = False
        return health_status
