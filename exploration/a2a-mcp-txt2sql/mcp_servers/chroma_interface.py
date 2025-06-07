"""
ChromaDB MCP interface using the mcp-use pattern.
"""

import asyncio
import json
import os
import uuid

import chromadb
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
CHROMA_DB_PATH = os.path.join(project_root, "data", "chroma_db")
print(f"✓ Using ChromaDB path: {CHROMA_DB_PATH}")

class ChromaDB:
    def __init__(self, db_path=CHROMA_DB_PATH):
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="system_interactions")

    def search_collection(self, query: str, n_results: int = 5) -> str:
        """Search a specific collection."""
        search_query = f"Search the '{self.collection.name}' collection for '{query}' and return {n_results} results"
        return search_query

    def search_interactions(self, query, n_results=5):
        # TODO fix this
        """Search similar interactions."""

        search_query = f"Search the {self.collection.name} collection for {query}"
        print(f"Search query: {search_query}")


        results = self.collection.query(
            query_texts=[search_query],
            n_results=n_results
        )

        return results

class ChromaMCP:
    def __init__(self, config_path="config/mcp_config.json"):
        self.config_path = config_path
        self.client = None
        self.agent = None

    async def initialize(self):
        """Initialize the Chroma MCP client and agent."""
        with open(self.config_path) as f:
            full_config = json.load(f)

        # Extract just chroma server
        chroma_config = {
            "mcpServers": {
                "chroma": full_config["mcpServers"]["chroma"]
            }
        }

        self.client = MCPClient.from_dict(chroma_config)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.agent = MCPAgent(llm=llm, client=self.client, max_steps=20)

        print("✓ ChromaDB MCP initialized")

    async def query(self, question: str) -> str:
        """Execute a natural language query against ChromaDB."""
        if not self.agent:
            raise RuntimeError("Call initialize() first")

        result = await self.agent.run(question)
        return result

    async def add_log(self, event_data: dict):
        """
        Adds a log to ChromaDB by prompting the agent to use the
        'chroma_add_documents' tool.
        """
        if not self.agent:
            raise RuntimeError("Call initialize() first")

        # 1. Prepare the arguments for the 'chroma_add_documents' tool.
        collection_name = "system_interactions"
        interaction_id = str(uuid.uuid4())

        # The 'document' is the text that gets embedded for vector search.
        # The user's query is the most semantically meaningful part for this.
        document_to_embed = event_data.get("user_query", "No user query provided.")

        # 2. Sanitize metadata: ChromaDB only accepts str, int, float, or bool.
        # We must convert complex types (like dicts or lists) to JSON strings
        # and ensure there are no 'None' values.
        clean_metadata = {}
        for key, value in event_data.items():
            if value is None:
                continue  # Skip None values entirely
            if isinstance(value, (dict, list)):
                clean_metadata[key] = json.dumps(value)
            else:
                clean_metadata[key] = value

        # 3. Construct a clear, explicit prompt for the agent.
        # This prompt makes it trivial for the LLM to map the information
        # to the arguments of the 'chroma_add_documents' tool.
        prompt = f"""
        Use the tool 'chroma_add_documents' to add a single document to the '{collection_name}' collection.

        - The document ID is: '{interaction_id}'
        - The document content to add is: '{document_to_embed}'
        - The metadata for the document is this JSON object: {json.dumps(clean_metadata)}
        """

        # 4. Execute the agent. The agent will parse the prompt, call the
        # tool with the correct arguments, and the MCP server will handle the rest.
        # We don't need the final chat response, we just need the tool call to happen.
        print(f"✓ Logging interaction {interaction_id} to ChromaDB...")
        await self.agent.run(prompt)

    @staticmethod
    def search_collection(collection_name: str, query: str, n_results: int = 5) -> str:
        """Search a specific collection."""
        search_query = f"Search the '{collection_name}' collection for '{query}' and return {n_results} results"
        return search_query


    async def close(self):
        """Clean up resources."""
        self.client = None
        self.agent = None


async def test():

    chroma_db = ChromaDB()
    print("ChromaDB: ", chroma_db.collection.get())
    results = chroma_db.search_interactions("how many entries are in the collection", 5)
    print(f"Results: {results}")


if __name__ == "__main__":
    asyncio.run(test())
