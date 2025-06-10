"""
Diagnostic tool to understand why MCP SQLite server becomes unresponsive.

This script will:
1. Test the MCP server directly without our application layer
2. Monitor process health during multiple queries
3. Capture detailed logs and timing
4. Help determine if the issue is server-side or client-side
"""

import asyncio
import json
import subprocess
import time
from datetime import datetime

import psutil
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient


class MCPDiagnostic:
    def __init__(self):
        self.config_path = "config/mcp_config.json"
        self.client = None
        self.agent = None
        self.server_process = None

    def get_server_processes(self):
        """Find MCP server processes."""
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "status", "cpu_percent", "memory_info"]
        ):
            try:
                cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
                if "mcp-server-sqlite" in cmdline or "sqlite" in cmdline.lower():
                    processes.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "cmdline": cmdline,
                            "status": proc.info["status"],
                            "cpu_percent": proc.info["cpu_percent"],
                            "memory_mb": proc.info["memory_info"].rss / 1024 / 1024
                            if proc.info["memory_info"]
                            else 0,
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    async def test_direct_mcp_server(self):
        """Test the MCP server directly using command line."""
        print("=" * 60)
        print("🔍 TESTING MCP SERVER DIRECTLY")
        print("=" * 60)

        # Load config
        with open(self.config_path) as f:
            config = json.load(f)

        sqlite_config = config["mcpServers"]["sqlite"]
        command = sqlite_config["command"]
        args = sqlite_config["args"]

        print(f"📋 Server command: {command}")
        print(f"📋 Server args: {args}")

        # Start server process manually
        full_command = [command] + args
        print(f"🚀 Starting MCP server: {' '.join(full_command)}")

        try:
            # Start the process
            process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            print(f"✅ Server started with PID: {process.pid}")

            # Send a simple MCP message
            test_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "diagnostic", "version": "1.0"},
                },
            }

            print("📤 Sending initialize message...")
            process.stdin.write(json.dumps(test_message) + "\n")
            process.stdin.flush()

            # Wait for response with timeout
            try:
                stdout, stderr = process.communicate(timeout=10)
                print(f"📥 Server response (stdout): {stdout}")
                if stderr:
                    print(f"⚠️ Server stderr: {stderr}")

            except subprocess.TimeoutExpired:
                print("⏰ Server did not respond within 10 seconds")
                process.kill()
                stdout, stderr = process.communicate()
                print(f"📥 Stdout after kill: {stdout}")
                print(f"⚠️ Stderr after kill: {stderr}")

        except Exception as e:
            print(f"❌ Failed to start server directly: {e}")

    async def test_mcp_client_lifecycle(self):
        """Test MCP client lifecycle with detailed monitoring."""
        print("\n" + "=" * 60)
        print("🔍 TESTING MCP CLIENT LIFECYCLE")
        print("=" * 60)

        # Monitor processes before
        print("📊 Process state BEFORE:")
        processes_before = self.get_server_processes()
        for proc in processes_before:
            print(
                f"  PID {proc['pid']}: {proc['name']} - {proc['status']} - CPU: {proc['cpu_percent']}% - Memory: {proc['memory_mb']:.1f}MB"
            )

        if not processes_before:
            print("  No MCP server processes found")

        # Load config and create client
        with open(self.config_path) as f:
            full_config = json.load(f)

        sqlite_server_config = {
            "mcpServers": {"sqlite": full_config["mcpServers"]["sqlite"]}
        }

        print("\n🔄 Creating MCP Client...")
        start_time = time.time()

        try:
            self.client = MCPClient.from_dict(sqlite_server_config)
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            self.agent = MCPAgent(llm=llm, client=self.client, max_steps=45)

            creation_time = time.time() - start_time
            print(f"✅ Client/Agent created in {creation_time:.2f}s")

            # Monitor processes after creation
            print("\n📊 Process state AFTER client creation:")
            processes_after = self.get_server_processes()
            for proc in processes_after:
                print(
                    f"  PID {proc['pid']}: {proc['name']} - {proc['status']} - CPU: {proc['cpu_percent']}% - Memory: {proc['memory_mb']:.1f}MB"
                )

            # Test multiple queries with detailed monitoring
            queries = [
                "How many artists are in the database?",
                "How many albums are in the database?",
                "How many tracks are in the database?",
                "List the first 3 artist names",
                "What are the table names in the database?",
            ]

            for i, query in enumerate(queries, 1):
                print(f"\n--- Query {i}: {query} ---")

                # Monitor before query
                processes_before_query = self.get_server_processes()
                print(f"📊 Processes before query {i}:")
                for proc in processes_before_query:
                    print(
                        f"  PID {proc['pid']}: {proc['status']} - CPU: {proc['cpu_percent']}% - Memory: {proc['memory_mb']:.1f}MB"
                    )

                # Execute query with timing
                query_start = time.time()
                try:
                    result = await asyncio.wait_for(self.agent.run(query), timeout=30.0)
                    query_time = time.time() - query_start
                    print(f"✅ Query {i} completed in {query_time:.2f}s")
                    print(f"📄 Result length: {len(str(result))} characters")

                    # Check for error indicators
                    if any(
                        indicator in str(result).lower()
                        for indicator in ["error", "failed", "cannot", "unable"]
                    ):
                        print(f"⚠️ Query {i} contains error indicators")

                except TimeoutError:
                    query_time = time.time() - query_start
                    print(f"⏰ Query {i} TIMED OUT after {query_time:.2f}s")

                except Exception as e:
                    query_time = time.time() - query_start
                    print(f"❌ Query {i} FAILED after {query_time:.2f}s: {e}")

                # Monitor after query
                processes_after_query = self.get_server_processes()
                print(f"📊 Processes after query {i}:")
                for proc in processes_after_query:
                    print(
                        f"  PID {proc['pid']}: {proc['status']} - CPU: {proc['cpu_percent']}% - Memory: {proc['memory_mb']:.1f}MB"
                    )

                # Check for process changes
                before_pids = {p["pid"] for p in processes_before_query}
                after_pids = {p["pid"] for p in processes_after_query}

                if before_pids != after_pids:
                    new_pids = after_pids - before_pids
                    dead_pids = before_pids - after_pids
                    if new_pids:
                        print(f"🆕 New processes: {new_pids}")
                    if dead_pids:
                        print(f"💀 Dead processes: {dead_pids}")

                # Wait between queries
                await asyncio.sleep(2)

        except Exception as e:
            print(f"❌ Client lifecycle test failed: {e}")
            import traceback

            traceback.print_exc()

        finally:
            # Final process check
            print("\n📊 Final process state:")
            final_processes = self.get_server_processes()
            for proc in final_processes:
                print(
                    f"  PID {proc['pid']}: {proc['name']} - {proc['status']} - CPU: {proc['cpu_percent']}% - Memory: {proc['memory_mb']:.1f}MB"
                )

    async def test_server_isolation(self):
        """Test if running the server externally helps."""
        print("\n" + "=" * 60)
        print("🔍 TESTING EXTERNAL SERVER MANAGEMENT")
        print("=" * 60)

        # This would involve starting the MCP server in a separate process
        # and then connecting to it, which is a more advanced test
        print("📝 TODO: Implement external server management test")
        print("   This would start the MCP server as a separate daemon/service")
        print("   and test if that improves reliability")

    async def run_full_diagnostic(self):
        """Run the complete diagnostic suite."""
        print("🔬 MCP SQLite Server Diagnostic Tool")
        print(f"⏰ Started at: {datetime.now()}")
        print(f"📁 Config: {self.config_path}")

        # Test 1: Direct server communication
        await self.test_direct_mcp_server()

        # Test 2: Client lifecycle
        await self.test_mcp_client_lifecycle()

        # Test 3: External server (placeholder)
        await self.test_server_isolation()

        print(f"\n✅ Diagnostic complete at: {datetime.now()}")


async def main():
    diagnostic = MCPDiagnostic()
    await diagnostic.run_full_diagnostic()


if __name__ == "__main__":
    asyncio.run(main())
