"""
Test that mimics our actual application flow to isolate the issue.
Since the MCP server works fine in isolation, the problem must be in 
our application's usage pattern.
"""

import asyncio
import uuid

from enhanced_orchestrator import EnhancedSQLOrchestrator


async def test_orchestrator_single_query():
    """Test single query through orchestrator."""
    print("🔍 Testing single query through orchestrator...")

    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()

    try:
        result = await orchestrator.run(
            user_query="How many artists are in the database?",
            thread_id=str(uuid.uuid4())
        )

        print("✅ Single orchestrator query succeeded")
        print(f"📄 Response: {result.get('final_response', 'No response')[:100]}...")
        return True

    except Exception as e:
        print(f"❌ Single orchestrator query failed: {e}")
        return False

    finally:
        await orchestrator.close()


async def test_orchestrator_multiple_queries_same_thread():
    """Test multiple queries through orchestrator with same thread."""
    print("\n🔍 Testing multiple queries through orchestrator (same thread)...")

    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()

    thread_id = str(uuid.uuid4())
    queries = [
        "How many artists are in the database?",
        "How many albums are in the database?",
        "How many tracks are in the database?"
    ]

    try:
        for i, query in enumerate(queries, 1):
            print(f"\n📤 Orchestrator Query {i}: {query}")

            result = await orchestrator.run(
                user_query=query,
                thread_id=thread_id  # Same thread ID
            )

            print(f"✅ Query {i} succeeded")
            print(f"📄 Response: {result.get('final_response', 'No response')[:100]}...")

        return True

    except Exception as e:
        print(f"❌ Orchestrator query failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await orchestrator.close()


async def test_orchestrator_multiple_queries_different_threads():
    """Test multiple queries through orchestrator with different threads."""
    print("\n🔍 Testing multiple queries through orchestrator (different threads)...")

    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()

    queries = [
        "How many artists are in the database?",
        "How many albums are in the database?",
        "How many tracks are in the database?"
    ]

    try:
        for i, query in enumerate(queries, 1):
            print(f"\n📤 Orchestrator Query {i}: {query}")

            result = await orchestrator.run(
                user_query=query,
                thread_id=str(uuid.uuid4())  # Different thread ID each time
            )

            print(f"✅ Query {i} succeeded")
            print(f"📄 Response: {result.get('final_response', 'No response')[:100]}...")

        return True

    except Exception as e:
        print(f"❌ Orchestrator query failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await orchestrator.close()


async def test_streamlit_simulation():
    """Simulate the exact Streamlit usage pattern."""
    print("\n🔍 Testing Streamlit simulation (persistent orchestrator)...")

    # This simulates how Streamlit keeps the orchestrator in session state
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()

    thread_id = str(uuid.uuid4())
    queries = [
        "How many artists are in the database?",
        "How many albums are in the database?",
        "How many tracks are in the database?"
    ]

    try:
        for i, query in enumerate(queries, 1):
            print(f"\n📤 Streamlit-style Query {i}: {query}")

            # This mimics exactly what Streamlit does
            result = await orchestrator.run(
                user_query=query,
                thread_id=thread_id
            )

            print(f"✅ Query {i} succeeded")
            print(f"📄 Response: {result.get('final_response', 'No response')[:100]}...")

            # Simulate time between user interactions
            await asyncio.sleep(1)

        return True

    except Exception as e:
        print(f"❌ Streamlit simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Don't close - this simulates Streamlit keeping it alive
        print("📝 Note: In Streamlit, orchestrator stays alive in session state")


async def test_mcp_isolation_layer():
    """Test the MCP isolation layer directly."""
    print("\n🔍 Testing MCP isolation layer directly...")

    from mcp_isolation import MCPIsolationLayer
    from mcp_servers.mcp_factory import create_mcp_interface

    # Create components using factory
    sqlite_mcp = await create_mcp_interface("sqlite")

    isolation_layer = MCPIsolationLayer()
    isolation_layer.register_server("sqlite", sqlite_mcp)

    queries = [
        "SELECT COUNT(*) FROM Artist",
        "SELECT COUNT(*) FROM Album",
        "SELECT COUNT(*) FROM Track"
    ]

    try:
        for i, sql_query in enumerate(queries, 1):
            print(f"\n📤 Isolation Layer Query {i}: {sql_query}")

            # Create mock LangGraph state
            mock_state = {
                "user_query": f"Query {i}",
                "sql_query": sql_query
            }

            response = await isolation_layer.execute_sql_query(mock_state)

            if response.success:
                print(f"✅ Query {i} succeeded")
                print(f"📄 Response: {response.content[:100]}...")
            else:
                print(f"❌ Query {i} failed: {response.error_message}")
                return False

        return True

    except Exception as e:
        print(f"❌ Isolation layer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await sqlite_mcp.close()


async def main():
    print("🧪 Application Flow Test Suite")
    print("Testing to find where MCP server becomes unresponsive...")

    # Test 1: Single query through orchestrator
    success1 = await test_orchestrator_single_query()

    if success1:
        # Test 2: Multiple queries same thread
        success2 = await test_orchestrator_multiple_queries_same_thread()

        if success2:
            # Test 3: Multiple queries different threads
            success3 = await test_orchestrator_multiple_queries_different_threads()

            if success3:
                # Test 4: Streamlit simulation
                success4 = await test_streamlit_simulation()

                if success4:
                    # Test 5: Isolation layer directly
                    success5 = await test_mcp_isolation_layer()

                    if success5:
                        print("\n✅ All application flow tests passed!")
                        print("🤔 The issue might be in specific query patterns or timing")
                    else:
                        print("\n❌ Isolation layer test failed")
                else:
                    print("\n❌ Streamlit simulation failed - this matches your issue!")
            else:
                print("\n❌ Multiple queries with different threads failed")
        else:
            print("\n❌ Multiple queries with same thread failed - LangGraph state issue!")
    else:
        print("\n❌ Single query through orchestrator failed")


if __name__ == "__main__":
    asyncio.run(main())
