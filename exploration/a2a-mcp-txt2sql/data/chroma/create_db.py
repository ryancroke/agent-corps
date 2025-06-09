"""
Setup ChromaDB for system memory logging.
"""

import json  # Import json to handle dictionary-like metadata
import os
import uuid
from datetime import datetime

import chromadb

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
CHROMA_DB_PATH = os.path.join(project_root, "data", "chroma_db")

def create_chroma_db():
    """Create ChromaDB collection for system interactions."""

    print(f"✓ Using ChromaDB path: {CHROMA_DB_PATH}")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    # Create collection with metadata
    collection = client.get_or_create_collection(
        name="system_interactions",
        metadata={"description": "A2A MCP system interaction logs"}
    )

    print(f"✓ Created collection: {collection.name}")
    print(f"✓ Current count: {collection.count()}")

    return client, collection


# --- CORRECTED FUNCTION ---
def add_interaction(collection, user_query, response, mcp_servers=None, agents=None, **kwargs):
    """Add interaction to ChromaDB."""

    interaction_id = str(uuid.uuid4())

    # Start with base metadata containing only required fields
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "session_id": kwargs.get("session_id", "default"),
        "user_query": user_query,
        "response": response,
        # Safely convert lists to strings
        "mcp_servers_used": str(mcp_servers or []),
        "agents_used": str(agents or []),
        "user_ip": kwargs.get("user_ip", "local")
    }

    # Conditionally add optional fields ONLY if they have a value
    # This prevents 'None' from ever being added.
    if "execution_time_ms" in kwargs:
        metadata["execution_time_ms"] = kwargs["execution_time_ms"]

    if "error" in kwargs and kwargs.get("error") is not None:
        metadata["error"] = str(kwargs["error"])

    if "sql_generated" in kwargs:
        metadata["sql_generated"] = kwargs["sql_generated"]

    if "validation_result" in kwargs:
        # Dictionaries must be converted to a string format like JSON
        metadata["validation_result"] = json.dumps(kwargs["validation_result"])

    if "workflow_path" in kwargs:
        metadata["workflow_path"] = str(kwargs["workflow_path"])

    # Add to collection (query text as document for embedding)
    collection.add(
        documents=[user_query],
        metadatas=[metadata],
        ids=[interaction_id]
    )

    print(f"✓ Added interaction: {interaction_id}")
    # For debugging, print the metadata that was just added
    # print(f"✓ Metadata: {metadata}")


def search_interactions(collection, query, n_results=5):
    """Search similar interactions."""

    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    return results


# Example usage
if __name__ == "__main__":
    client, collection = create_chroma_db()

    # Test interaction (this will now work)
    add_interaction(
        collection,
        user_query="How many artists are in the database?",
        response="There are 277 artists in the database.",
        mcp_servers=["sqlite", "python_repl"],
        agents=["orchestrator", "sql_validator"],
        execution_time_ms=1250,
        sql_generated="SELECT COUNT(*) FROM Artist",
        validation_result={"is_valid": True, "safe": True}
    )

    # Test an interaction with an error
    add_interaction(
        collection,
        user_query="DROP TABLE *",
        response="I'm sorry, I cannot perform that action.",
        error="Disallowed SQL keyword 'DROP' detected.",
        validation_result={"is_valid": False, "safe": False}
    )

    # Search test
    results = search_interactions(collection, "artists count")
    print(f"\nFound {len(results['documents'][0])} similar interactions for 'artists count':")
    for _doc, meta in zip(results['documents'][0], results['metadatas'][0], strict=False):
        print(f"  - Query: {meta['user_query']}")
        print(f"    Response: {meta['response']}")
