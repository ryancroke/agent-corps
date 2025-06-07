"""
SQLite MCP interface for connecting to the standard multi-tool server.
"""

import asyncio
import json
import uuid
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

# Import isolation layer types
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_isolation import MCPQueryContext, MCPResponse, MCPServer

load_dotenv()


class SQLiteMCP:
    def __init__(self,config_path="config/mcp_config.json"):
        self.config_path = config_path
        self.client = None
        self.agent = None
        self.connection_id = str(uuid.uuid4())[:8]
        self.initialized_at = None
        self.query_count = 0
        self.last_query_time = None

    async def initialize(self):
        """Initialize the SQLite MCP client and agent."""
        try:
            with open(self.config_path) as f:
                full_config = json.load(f)

            # Extract just sqlite server
            sqlite_server_config = {
                "mcpServers": {
                    "sqlite": full_config["mcpServers"]["sqlite"]
                }
            }

            self.client = MCPClient.from_dict(sqlite_server_config)
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            self.agent = MCPAgent(llm=llm, client=self.client, max_steps=45)
            
            self.initialized_at = datetime.now()
            
        except Exception as e:
            print(f"❌ SQLiteMCP initialization failed: {e}")
            raise

    async def query(self, task_description: str) -> str:
        """
        Sends a natural language task to the agent. The agent will decide
        which tool (e.g., read_query, list_tables) to use.
        """
        self.query_count += 1
        self.last_query_time = datetime.now()
        
        if not self.agent:
            raise RuntimeError(f"SQLiteMCP - Call initialize() first")

        try:
            result = await self.agent.run(task_description)
            return result
        except Exception as e:
            print(f"❌ SQLiteMCP query failed: {e}")
            raise



    async def health_check(self) -> bool:
        """Check if the MCP connection is healthy."""
        if not self.agent or not self.client:
            return False
            
        try:
            result = await self.agent.run("List the names of all tables in the database")
            success = "error" not in str(result).lower() and len(str(result)) > 0
            return success
        except Exception as e:
            print(f"❌ SQLiteMCP health check failed: {e}")
            return False

    def get_connection_info(self) -> dict:
        """Get debugging info about the connection."""
        return {
            "connection_id": self.connection_id,
            "initialized_at": self.initialized_at.isoformat() if self.initialized_at else None,
            "query_count": self.query_count,
            "last_query_time": self.last_query_time.isoformat() if self.last_query_time else None,
            "client_connected": self.client is not None,
            "agent_available": self.agent is not None,
            "client_id": id(self.client) if self.client else None,
            "agent_id": id(self.agent) if self.agent else None,
        }

    async def close(self):
        """Clean up resources."""
        self.client = None
        self.agent = None

    async def execute_query(self, context: MCPQueryContext) -> MCPResponse:
        """
        Clean isolation layer interface - implements MCPServer protocol.
        """
        if context.query_type != "sql" or not context.sql_query:
            return MCPResponse(
                success=False,
                content="",
                error_message="Invalid query context - SQL query required"
            )
        
        # Create clean task description
        task_description = f"Execute this SQL query: {context.sql_query}"
        
        try:
            result = await self.query(task_description)
            
            # Check for error indicators in the response
            error_indicators = ["error", "failed", "cannot", "unable", "exception", "invalid", "issue", "problem", "try again"]
            result_lower = str(result).lower()
            found_errors = [indicator for indicator in error_indicators if indicator in result_lower]
            
            if found_errors:
                return MCPResponse(
                    success=False,
                    content=str(result),
                    error_message=f"Query execution returned error indicators: {found_errors}",
                    metadata={"error_indicators": found_errors}
                )
            else:
                return MCPResponse(
                    success=True,
                    content=str(result),
                    metadata={
                        "query_executed": context.sql_query,
                        "execution_method": "standard"
                    }
                )
                
        except Exception as e:
            return MCPResponse(
                success=False,
                content="",
                error_message=f"Query execution exception: {str(e)}",
                metadata={"exception_type": type(e).__name__}
            )


# Example usage to verify the connection and tools
async def test():
    print("--- Testing SQLite MCP Interface ---")
    sqlite_interface = SQLiteMCP()
    await sqlite_interface.initialize()

    # Test 1: A task that should use the 'read_query' tool
    print("\n--- TEST 1: Simple Query ---")
    result1 = await sqlite_interface.query("How many artists are in the database?")
    print(f"Result 1: {result1}")

    # Test 2: A task that should use the 'list_tables' tool
    print("\n--- TEST 2: List Tables ---")
    result2 = await sqlite_interface.query("What are the names of the tables in the database?")
    print(f"Result 2: {result2}")

    await sqlite_interface.close()


if __name__ == "__main__":
    asyncio.run(test())
