"""
Generic MCP interface using factory pattern.
Eliminates duplicate code across MCP server implementations.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

load_dotenv()


class MCPInterface:
    """Generic wrapper for any MCP server using mcp-use pattern"""
    
    def __init__(self, server_name: str, client: MCPClient, agent: MCPAgent):
        self.server_name = server_name
        self.client = client
        self.agent = agent
        self.connection_id = str(uuid.uuid4())[:8]
        self.initialized_at = datetime.now()
        self.query_count = 0
        self.last_query_time: Optional[datetime] = None

    async def query(self, task_description: str) -> str:
        """
        Sends a natural language task to the agent. The agent will decide
        which tool to use based on the server's available tools.
        """
        self.query_count += 1
        self.last_query_time = datetime.now()
        
        if not self.agent:
            raise RuntimeError(f"{self.server_name}MCP - Not initialized")

        try:
            result = await self.agent.run(task_description)
            return result
        except Exception as e:
            print(f"❌ {self.server_name}MCP query failed: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if the MCP connection is healthy"""
        if not self.agent or not self.client:
            return False
        try:
            # Try a simple operation - customize per server type if needed
            if self.server_name == "sqlite":
                result = await self.agent.run("List the names of all tables in the database")
            elif self.server_name == "chroma":
                result = await self.agent.run("List available collections")
            else:
                result = await self.agent.run("Perform a simple test operation")
            
            success = "error" not in str(result).lower() and len(str(result)) > 0
            return success
        except Exception as e:
            print(f"❌ {self.server_name}MCP health check failed: {e}")
            return False

    def get_connection_info(self) -> dict:
        """Get debugging info about the connection."""
        return {
            "server_name": self.server_name,
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
        """Clean up resources"""
        self.client = None
        self.agent = None


async def create_mcp_interface(
    server_name: str, 
    config_path: str = "config/mcp_config.json",
    model: str = "gpt-4o-mini",
    temperature: float = 0,
    max_steps: int = 45
) -> MCPInterface:
    """
    Create any MCP interface from config with customizable parameters.
    
    Args:
        server_name: Name of the server in mcp_config.json (e.g., "sqlite", "chroma")
        config_path: Path to the MCP configuration file
        model: LLM model to use for the agent
        temperature: Temperature setting for the LLM
        max_steps: Maximum steps the agent can take
    
    Returns:
        MCPInterface: Initialized MCP interface ready to use
    """
    try:
        # Load config and extract server section
        with open(config_path) as f:
            full_config = json.load(f)
        
        if server_name not in full_config["mcpServers"]:
            raise ValueError(f"Server '{server_name}' not found in config. Available: {list(full_config['mcpServers'].keys())}")
        
        server_config = {
            "mcpServers": {
                server_name: full_config["mcpServers"][server_name]
            }
        }
        
        # Create using mcp-use pattern with configurable parameters
        client = MCPClient.from_dict(server_config)
        llm = ChatOpenAI(model=model, temperature=temperature)
        agent = MCPAgent(llm=llm, client=client, max_steps=max_steps)
        
        print(f"✓ {server_name}MCP interface created successfully")
        return MCPInterface(server_name, client, agent)
        
    except Exception as e:
        print(f"❌ Failed to create {server_name}MCP interface: {e}")
        raise


# Example usage and testing
async def test_mcp_factory():
    """Test the MCP factory with different servers"""
    
    print("--- Testing MCP Factory ---")
    
    # Test SQLite MCP
    print("\n--- TEST: SQLite MCP ---")
    sqlite_mcp = await create_mcp_interface("sqlite")
    result1 = await sqlite_mcp.query("How many artists are in the database?")
    print(f"SQLite Result: {result1}")
    print(f"SQLite Connection Info: {sqlite_mcp.get_connection_info()}")
    
    # Test Chroma MCP with different parameters
    print("\n--- TEST: Chroma MCP ---")
    chroma_mcp = await create_mcp_interface(
        "chroma", 
        model="gpt-4o-mini", 
        max_steps=20
    )
    health = await chroma_mcp.health_check()
    print(f"Chroma Health: {health}")
    print(f"Chroma Connection Info: {chroma_mcp.get_connection_info()}")
    
    # Cleanup
    await sqlite_mcp.close()
    await chroma_mcp.close()


if __name__ == "__main__":
    asyncio.run(test_mcp_factory())