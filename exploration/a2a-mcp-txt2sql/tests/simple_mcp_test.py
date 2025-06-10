"""
Simple test to isolate MCP server issues without complex diagnostics.
"""

import asyncio
import json

from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient


async def test_single_query():
    """Test just one query to isolate the issue."""
    print("🔍 Testing single MCP query...")

    # Load config
    with open("config/mcp_config.json") as f:
        full_config = json.load(f)

    sqlite_server_config = {
        "mcpServers": {"sqlite": full_config["mcpServers"]["sqlite"]}
    }

    print("🔄 Creating MCP Client...")
    client = MCPClient.from_dict(sqlite_server_config)

    print("🔄 Creating LLM and Agent...")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = MCPAgent(llm=llm, client=client, max_steps=10)  # Reduced max_steps

    print("📤 Sending simple query...")
    try:
        result = await asyncio.wait_for(agent.run("List table names"), timeout=15.0)
        print(f"✅ Query succeeded: {result}")
        return True

    except TimeoutError:
        print("⏰ Query timed out")
        return False

    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False


async def test_multiple_queries():
    """Test multiple queries with the same client/agent."""
    print("\n🔍 Testing multiple queries with same client...")

    # Load config
    with open("config/mcp_config.json") as f:
        full_config = json.load(f)

    sqlite_server_config = {
        "mcpServers": {"sqlite": full_config["mcpServers"]["sqlite"]}
    }

    print("🔄 Creating MCP Client...")
    client = MCPClient.from_dict(sqlite_server_config)

    print("🔄 Creating LLM and Agent...")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = MCPAgent(llm=llm, client=client, max_steps=10)

    queries = [
        "List table names",
        "Count rows in Artist table",
        "Count rows in Album table",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n📤 Query {i}: {query}")
        try:
            result = await asyncio.wait_for(agent.run(query), timeout=15.0)
            print(f"✅ Query {i} succeeded: {str(result)[:100]}...")

        except TimeoutError:
            print(f"⏰ Query {i} timed out")
            return False

        except Exception as e:
            print(f"❌ Query {i} failed: {e}")
            return False

    return True


async def test_fresh_clients():
    """Test multiple queries with fresh clients each time."""
    print("\n🔍 Testing multiple queries with fresh clients...")

    queries = [
        "List table names",
        "Count rows in Artist table",
        "Count rows in Album table",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n📤 Query {i} with fresh client: {query}")

        # Create fresh client/agent for each query
        with open("config/mcp_config.json") as f:
            full_config = json.load(f)

        sqlite_server_config = {
            "mcpServers": {"sqlite": full_config["mcpServers"]["sqlite"]}
        }

        client = MCPClient.from_dict(sqlite_server_config)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        agent = MCPAgent(llm=llm, client=client, max_steps=10)

        try:
            result = await asyncio.wait_for(agent.run(query), timeout=15.0)
            print(f"✅ Query {i} succeeded: {str(result)[:100]}...")

        except TimeoutError:
            print(f"⏰ Query {i} timed out")
            return False

        except Exception as e:
            print(f"❌ Query {i} failed: {e}")
            return False

    return True


async def main():
    print("🧪 Simple MCP Test Suite")

    # Test 1: Single query
    success1 = await test_single_query()

    if success1:
        # Test 2: Multiple queries same client
        success2 = await test_multiple_queries()

        if success2:
            # Test 3: Multiple queries fresh clients
            success3 = await test_fresh_clients()

            if success3:
                print("\n✅ All tests passed! MCP server seems healthy.")
            else:
                print("\n❌ Fresh client test failed")
        else:
            print("\n❌ Multiple query test failed - this is likely our issue!")
    else:
        print("\n❌ Single query test failed - server has fundamental issues")


if __name__ == "__main__":
    asyncio.run(main())
