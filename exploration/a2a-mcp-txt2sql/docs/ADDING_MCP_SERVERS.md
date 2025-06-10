# Adding MCP Servers to A2A SQL Chat

This guide walks you through adding new MCP (Model Context Protocol) servers to extend the capabilities of the A2A SQL Chat application.

## Overview

MCP servers provide direct access to external resources like databases, APIs, file systems, and web services. Our architecture uses a **factory pattern** that makes adding new MCP servers straightforward.

## Current MCP Servers

The application currently includes:
- **SQLite MCP**: Database operations on Chinook music database
- **ChromaDB MCP**: Vector database for conversation logging and search
- **Python REPL MCP**: Code execution for SQL validation

## Step-by-Step Integration Process

### Step 1: MCP Server Setup & Configuration

#### 1.1. Install/Setup the MCP Server

Depending on the MCP server type, you may need to:

**Option A: Install via Package Manager**
```bash
# Example: Install a packaged MCP server
uvx install github-mcp-server
npm install @anthropic-ai/mcp-server-filesystem
```

**Option B: Clone and Build from Source**
```bash
# Example: Build custom MCP server
git clone https://github.com/example/custom-mcp-server
cd custom-mcp-server
uv sync  # or npm install
```

**Option C: Use Existing Service**
```bash
# Example: External API that provides MCP interface
# No installation needed, just configuration
```

#### 1.2. Add to MCP Configuration

Edit `config/mcp_config.json` to include your new server:

```json
{
  "mcpServers": {
    "sqlite": { ... },
    "chroma": { ... },
    "your_new_server": {
      "command": "uvx",
      "args": [
        "your-mcp-server-package",
        "--param1", "value1",
        "--param2", "value2"
      ]
    }
  }
}
```

**Common MCP Server Patterns:**

```json
{
  "mcpServers": {
    // File system access
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-filesystem", "/path/to/allowed/directory"]
    },
    
    // GitHub integration
    "github": {
      "command": "uvx",
      "args": ["github-mcp-server", "--github-personal-access-token", "your_token"]
    },
    
    // Web search
    "search": {
      "command": "uvx", 
      "args": ["search-mcp-server", "--api-key", "your_search_api_key"]
    },
    
    // Custom database
    "postgres": {
      "command": "uv",
      "args": [
        "--directory", "path/to/postgres-mcp",
        "run", "postgres-mcp-server",
        "--connection-string", "postgresql://user:pass@localhost:5432/db"
      ]
    },
    
    // External API
    "weather": {
      "command": "python",
      "args": ["-m", "weather_mcp_server", "--api-key", "weather_api_key"]
    }
  }
}
```

### Step 2: LangGraph Integration

The integration complexity depends on how the MCP server will be used in your workflow.

#### 2.1. Simple Integration (Direct Access)

For MCP servers that provide **direct data access** without complex workflows:

**Edit `enhanced_orchestrator.py`:**

```python
async def initialize(self):
    """Initialize all components."""
    # Existing servers
    self.sqlite_mcp = await create_mcp_interface("sqlite")
    self.chroma_logger = await create_mcp_interface("chroma")
    
    # Add your new server
    self.your_new_mcp = await create_mcp_interface("your_new_server")
    
    # Register with isolation layer (optional)
    self.mcp_isolation.register_server("your_new_server", self.your_new_mcp)
    
    # ... rest of initialization
```

**Add to cleanup:**
```python
async def close(self):
    """Clean up resources."""
    if self.sqlite_mcp:
        await self.sqlite_mcp.close()
    if self.chroma_logger:
        await self.chroma_logger.close()
    if self.your_new_mcp:  # Add cleanup
        await self.your_new_mcp.close()
```

#### 2.2. Complex Integration (New Workflow Nodes)

For MCP servers that require **new LangGraph nodes and routing logic**:

**A. Add State Fields (if needed):**
```python
class State(TypedDict):
    # Existing fields...
    your_service_query: str
    your_service_result: str
    needs_your_service: bool
```

**B. Add Node Function:**
```python
async def _query_your_service(self, state: State) -> State:
    """Query your new MCP service."""
    try:
        # Use the MCP interface
        query = f"Perform operation: {state['your_service_query']}"
        result = await self.your_new_mcp.query(query)
        
        mcp_servers_used = state.get("mcp_servers_used", []) + ["your_new_mcp"]
        
        return {
            **state,
            "your_service_result": str(result),
            "final_response": str(result),
            "mcp_servers_used": mcp_servers_used,
        }
        
    except Exception as e:
        print(f"❌ Your service query failed: {e}")
        return {
            **state,
            "your_service_result": f"Error: {str(e)}",
            "final_response": f"Service query failed: {str(e)}",
            "mcp_servers_used": state.get("mcp_servers_used", []) + ["your_new_mcp_error"],
        }
```

**C. Update Graph Building:**
```python
def _build_graph(self):
    """Build LangGraph with A2A validation."""
    graph = StateGraph(State)
    
    # Existing nodes...
    graph.add_node("query_your_service", self._query_your_service)
    
    # Update routing logic in _route_query method
    # Update conditional edges in _route_decision method
```

**D. Update Routing Logic:**
```python
async def _route_query(self, state: State) -> State:
    """Decide query type: SQL, memory search, your service, or direct response."""
    query = state['user_query']
    
    routing_prompt = f"""
    Analyze this user query and determine the best routing:
    
    Query: {query}
    
    Choose ONE of these options:
    - SQL: Query needs database access (artists, albums, tracks, sales data)
    - MEMORY: Query asks about previous conversations, history, or similar interactions
    - YOUR_SERVICE: Query needs [describe your service capability]
    - DIRECT: General question that needs a direct LLM response
    
    Examples:
    - "How many artists are there?" → SQL
    - "What did we talk about earlier?" → MEMORY
    - "[Example query for your service]" → YOUR_SERVICE
    - "What is Python?" → DIRECT
    
    Respond with exactly one word: SQL, MEMORY, YOUR_SERVICE, or DIRECT
    """
    
    response = await self.llm.ainvoke(routing_prompt)
    route_decision = response.content.strip().upper()
    
    # Set routing flags
    needs_sql = route_decision == "SQL"
    needs_memory = route_decision == "MEMORY"
    needs_your_service = route_decision == "YOUR_SERVICE"
    query_type = route_decision.lower()
    
    return {
        **state,
        "needs_sql": needs_sql,
        "needs_memory": needs_memory,
        "needs_your_service": needs_your_service,
        "query_type": query_type,
    }

def _route_decision(self, state: State) -> str:
    """Route based on query type."""
    if state["needs_sql"]:
        return "generate_sql"
    elif state["needs_memory"]:
        return "search_memory"
    elif state["needs_your_service"]:
        return "query_your_service"
    else:
        return "direct_response"
```

### Step 3: Health Checks and Factory Updates

#### 3.1. Custom Health Check (Optional)

If your MCP server needs a custom health check, update `mcp_factory.py`:

```python
async def health_check(self) -> bool:
    """Check if the MCP connection is healthy"""
    if not self.agent or not self.client:
        return False
    try:
        # Add your custom health check
        if self.server_name == "your_new_server":
            result = await self.agent.run("Perform health check operation")
        elif self.server_name == "sqlite":
            result = await self.agent.run("List the names of all tables in the database")
        # ... existing health checks
        
        success = "error" not in str(result).lower() and len(str(result)) > 0
        return success
    except Exception as e:
        print(f"❌ {self.server_name}MCP health check failed: {e}")
        return False
```

### Step 4: Frontend Integration (Optional)

#### 4.1. Add Health Check Display

Update `fastapi_app.py` health endpoint to include your new server:

```python
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not ready")

    # Check all MCP servers
    sqlite_healthy = await orchestrator.sqlite_mcp.health_check()
    chroma_healthy = await orchestrator.chroma_logger.health_check()
    your_service_healthy = await orchestrator.your_new_mcp.health_check()

    overall_healthy = sqlite_healthy and chroma_healthy and your_service_healthy

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "orchestrator": "ready",
        "mcp_servers": {
            "sqlite": "healthy" if sqlite_healthy else "unhealthy",
            "chroma": "healthy" if chroma_healthy else "unhealthy", 
            "your_service": "healthy" if your_service_healthy else "unhealthy",
        },
        "timestamp": datetime.now().isoformat(),
    }
```

#### 4.2. Update Frontend (Optional)

If you want to show your service status in the UI, update `static/app.js`:

```javascript
// Add to the health check display
function updateHealthStatus(health) {
    const statusElement = document.getElementById('health-status');
    const isHealthy = health.status === 'healthy';
    
    statusElement.innerHTML = `
        <div class="health-indicator ${isHealthy ? 'healthy' : 'degraded'}">
            <span class="status-dot"></span>
            <div class="status-details">
                <div>System: ${health.status}</div>
                <div>SQLite: ${health.mcp_servers?.sqlite || 'unknown'}</div>
                <div>ChromaDB: ${health.mcp_servers?.chroma || 'unknown'}</div>
                <div>Your Service: ${health.mcp_servers?.your_service || 'unknown'}</div>
            </div>
        </div>
    `;
}
```

## MCP Server Type-Specific Patterns

### Database Servers
```python
# Routing: Add to SQL routing or create separate database routing
# Nodes: Similar to execute_sql but for your database
# State: May need connection_string, query_result fields
```

### API Servers  
```python
# Routing: Create API-specific routing based on query content
# Nodes: API request/response handling with error management
# State: Add api_endpoint, api_params, api_response fields
```

### File System Servers
```python
# Routing: File operation detection (read, write, list, search)
# Nodes: File operation nodes with proper error handling
# State: Add file_path, file_content, file_operation fields
```

### Search/Web Servers
```python
# Routing: Web search intent detection
# Nodes: Search execution with result formatting
# State: Add search_query, search_results, source_urls fields
```

## Testing Your Integration

### 1. Test MCP Server Directly
```bash
# Test the factory pattern
uv run mcp_servers/mcp_factory.py

# Should now include your new server in the test output
```

### 2. Test Integration
```bash
# Test orchestrator with your new server
uv run enhanced_orchestrator.py

# Test via API
uv run fastapi_app.py
# Then test queries that should route to your service
```

### 3. Add Integration Tests
Create `tests/test_your_service_integration.py`:

```python
import asyncio
from enhanced_orchestrator import EnhancedSQLOrchestrator

async def test_your_service():
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()
    
    result = await orchestrator.run(
        "Test query for your service",
        "test-thread"
    )
    
    assert "your_service" in result.get("mcp_servers_used", [])
    print(f"Your service result: {result.get('final_response')}")
    
    await orchestrator.close()

if __name__ == "__main__":
    asyncio.run(test_your_service())
```

## Troubleshooting

### Common Issues

1. **MCP Server Won't Start**
   - Check command path in config
   - Verify all dependencies are installed
   - Check file permissions

2. **Factory Creation Fails**
   - Verify server name matches config
   - Check for relative path resolution issues
   - Ensure server responds to initialize message

3. **Routing Not Working**
   - Update routing prompt with clear examples
   - Test routing logic with sample queries
   - Check conditional edge logic

4. **Health Checks Failing**
   - Customize health check for your server
   - Verify server accepts the test operation
   - Check timeout settings

### Debug Commands

```bash
# Test MCP server isolation
uv run tests/diagnostic_mcp.py

# Test factory pattern
python -c "
import asyncio
from mcp_servers.mcp_factory import create_mcp_interface

async def test():
    mcp = await create_mcp_interface('your_server')
    health = await mcp.health_check()
    print(f'Health: {health}')
    await mcp.close()

asyncio.run(test())
"
```

## Best Practices

1. **Configuration Management**
   - Use environment variables for secrets
   - Keep relative paths for portability
   - Document required external setup

2. **Error Handling**
   - Always handle MCP server failures gracefully
   - Provide meaningful error messages to users
   - Add fallback behavior when possible

3. **Performance**
   - Consider caching for expensive operations
   - Add timeout handling for slow services
   - Monitor connection health

4. **Security**
   - Validate inputs to MCP servers
   - Limit file system access appropriately
   - Sanitize API responses

## Next Steps

After adding an MCP server, consider:
- Adding A2A agents that coordinate multiple MCP servers
- Creating custom frontend components for your service
- Adding monitoring and metrics
- Writing comprehensive tests

See [`ADDING_A2A_AGENTS.md`](ADDING_A2A_AGENTS.md) for the next level of integration.