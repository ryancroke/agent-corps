"""
Updated SQLite MCP interface to connect to the standard, multi-tool
server running in Docker.
"""

import asyncio
import json

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

load_dotenv()


class SQLiteMCP:
    def __init__(self,config_path="config/mcp_config.json"):
        self.config_path = config_path
        self.client = None
        self.agent = None

    async def initialize(self):
        """Initialize the Chroma MCP client and agent."""
        with open(self.config_path) as f:
            full_config = json.load(f)

        # Extract just chroma server
        sqlite_server_config = {
            "mcpServers": {
                "sqlite": full_config["mcpServers"]["sqlite"]
            }
        }

        self.client = MCPClient.from_dict(sqlite_server_config)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        # This agent now has access to all the tools on the standard server:
        # read_query, list_tables, describe-table, etc.
        self.agent = MCPAgent(llm=llm, client=self.client, max_steps=15)

        print("✓ SQLite MCP Interface initialized")

    async def query(self, task_description: str) -> str:
        """
        Sends a natural language task to the agent. The agent will decide
        which tool (e.g., read_query, list_tables) to use.
        """
        if not self.agent:
            raise RuntimeError("Call initialize() first")

        print(f"▶️  Sending task to SQLite Agent: '{task_description}'")
        result = await self.agent.run(task_description)
        return result

    async def close(self):
        """Clean up resources."""
        self.client = None
        self.agent = None


# Example usage to verify the connection and tools
async def test():
    # Make sure your Docker container is running before executing this test
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
    # To run this file directly for testing:
    # 1. Make sure the Docker container with the MCP server is running.
    # 2. Run `uv run sqlite_interface.py` in your terminal.
    asyncio.run(test())
