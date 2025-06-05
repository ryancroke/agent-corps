import asyncio
import json
from pathlib import Path
from mcp_use import MCPAgent, MCPClient
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


class SQLiteMCP:
    def __init__(self, config_path="config/mcp_config.json"):
        self.config_path = config_path
        self.client = None
        self.agent = None
    
    async def initialize(self):
        """Initialize the MCP client and agent."""
        with open(self.config_path, 'r') as f:
            config = json.load(f)
        
        self.client = MCPClient.from_dict(config)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.agent = MCPAgent(llm=llm, client=self.client, max_steps=10)
        
        print("✓ SQLite MCP initialized")
    
    async def query(self, question: str) -> str:
        """Execute a natural language query against the database."""
        if not self.agent:
            raise RuntimeError("Call initialize() first")
        
        result = await self.agent.run(question)
        return result
    
    async def close(self):
        """Clean up resources."""
        self.client = None
        self.agent = None


# Example usage
async def test():
    sqlite = SQLiteMCP()
    await sqlite.initialize()
    
    result = await sqlite.query("How many artists are in the database?")
    print(f"Result: {result}")
    
    await sqlite.close()


if __name__ == "__main__":
    asyncio.run(test())