# SQL Chat AI

**sophisticated AI-powered chat interface for exploring the Chinook music database using Agent-to-Agent (A2A) validation and Model Context Protocol (MCP) servers.**

## Features

### **Intelligent SQL Generation & Validation**

- **Natural Language to SQL**: Ask questions in plain English, get accurate SQL queries
- **A2A Validation**: SQL queries are validated by a dedicated agent before execution
- **Safety First**: Prevents dangerous operations like DROP, DELETE without WHERE clauses
- **Smart Context**: Understands conversation history for follow-up questions

### **Modern Architecture**

- **FastAPI Backend**: High-performance async Python backend
- **MCP Integration**: Uses Model Context Protocol for database operations
- **LangGraph Orchestration**: Sophisticated workflow management with state persistence
- **Web-Native Frontend**: Beautiful, responsive HTML/CSS/JS interface

### **Real-Time Experience**

- **Instant Responses**: No hanging or timeout issues (unlike Streamlit!)
- **Live SQL Display**: See the generated SQL queries alongside results
- **Health Monitoring**: Real-time server status indicators
- **Example Queries**: Quick-start suggestions for exploring the database

### **Database Exploration**

- **Chinook Music Database**: Explore artists, albums, tracks, customers, and sales
- **Complex Queries**: Handle joins, aggregations, filtering, and sorting
- **Data Insights**: Get meaningful answers about music trends and patterns

## Quick Start

### Prerequisites

- Python 3.11+
- UV package manager

### 1. Install Dependencies

```bash
uv sync
```

### 2. Install DENO (for python REPL)

```bash
curl -fsSL https://deno.land/install.sh | sh
```

### 3. Start the Application

```bash
uv run fastapi_app.py
```

### 4. Open Your Browser

Navigate to: http://localhost:8000

## Try These Example Queries

- "How many artists are in the database?"
- "What are the top 5 best-selling albums?"
- "Which genre has the most tracks?"
- "Show me all customers from Brazil"
- "What's the average track length by genre?"
- "Which artist has the most albums?"

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detailed technical architecture.

## Extension Guides

- 📚 [Adding MCP Servers](docs/ADDING_MCP_SERVERS.md) - Integrate new data sources and external services
- 🤖 [Adding A2A Agents](docs/ADDING_A2A_AGENTS.md) - Create intelligent workflow agents

### **Backend Components**

#### FastAPI Application

Enhanced SQL Orchestrator (LangGraph)

* Query Contextualization
* SQL Generation (GPT-4o-mini)
* A2A Validation Agent
* MCP SQL Execution

MCP Servers

* SQLite MCP (Database Operations)
* ChromaDB MCP (Interaction Logging)
* Python REPL MCP (SQL Validation)

Isolation Layer (Clean State Management)

### **Frontend Components**

Web Interface

* Modern HTML5/CSS3 UI
* Vanilla JavaScript (No Framework Bloat)
* Real-time Chat Interface
* SQL Query Display
* Health Status Monitoring

## Technical Details

### **MCP (Model Context Protocol)**

- **SQLite Server**: Handles database operations via standardized protocol
- **ChromaDB Server**: Logs interactions for analysis and debugging
- **Python REPL Server**: Validates SQL queries for safety
- **Factory Pattern**: Clean, configurable MCP server creation and management

### **LangGraph Workflow**

1. **Contextualization**: Rewrite user query with conversation history
2. **Routing**: Determine if query needs database access
3. **SQL Generation**: Convert natural language to SQL
4. **A2A Validation**: Safety and correctness validation
5. **Execution**: Run validated SQL through MCP isolation layer
6. **Logging**: Store interaction for future analysis

### **Agent-to-Agent (A2A) Validation**

- **SQL Syntax Validation**: Ensures query is syntactically correct
- **Safety Checks**: Prevents destructive operations
- **Logic Validation**: Verifies query makes sense for the schema
- **Performance Hints**: Suggests optimizations when needed

### **MCP Factory Pattern**

- **Unified Interface**: Single `create_mcp_interface()` function for all MCP servers
- **Configurable Parameters**: Customize model, temperature, max_steps per server
- **Eliminates Duplication**: No more duplicate initialization code across server types
- **Easy Extension**: Add new MCP servers by simply updating config and calling factory
- **Type Safety**: Consistent interface for all MCP server interactions

```python
# Clean factory usage
sqlite_mcp = await create_mcp_interface("sqlite")
chroma_mcp = await create_mcp_interface("chroma", model="gpt-3.5-turbo")
custom_mcp = await create_mcp_interface("new_server", temperature=0.2, max_steps=20)
```

## Project Structure

```
.
├── fastapi_app.py             # Main FastAPI application
├── enhanced_orchestrator.py   # LangGraph orchestration logic
├── mcp_isolation.py          # Clean MCP server interface
├── agents/
│   └── sql_validation_agent.py # A2A validation agent
├── mcp_servers/
│   └── mcp_factory.py        # MCP factory pattern implementation
├── static/                   # Frontend assets
│   ├── index.html           # Main web interface
│   ├── styles.css           # Beautiful styling
│   └── app.js               # Interactive JavaScript
├── config/
│   ├── mcp_config.json      # MCP server configuration
│   └── settings.yaml        # Application settings
├── data/
│   └── Chinook_Sqlite.db    # Music database
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # Technical architecture details
│   ├── ADDING_MCP_SERVERS.md # Guide for adding MCP servers
│   └── ADDING_A2A_AGENTS.md # Guide for adding A2A agents
└── tests/                   # Test files
    ├── test_app_flow.py     # Integration tests
    ├── simple_mcp_test.py   # MCP connectivity tests
    └── diagnostic_mcp.py    # MCP diagnostic tool
```

## Configuration

### **MCP Server Configuration** (`config/mcp_config.json`)

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uv",
      "args": ["--directory", "path/to/sqlite", "run", "mcp-server-sqlite", "--db-path", "data/Chinook_Sqlite.db"]
    },
    "chroma": {
      "command": "uvx",
      "args": ["chroma-mcp", "--client-type", "persistent", "--data-dir", "data/chroma_db"]
    }
  }
}
```

## Development Commands

### **Code Quality**

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy .

# Fix lint issues
ruff check --fix .
```

### **Testing**

```bash
# Test MCP factory pattern
uv run mcp_servers/mcp_factory.py

# Test enhanced orchestrator
uv run enhanced_orchestrator.py

# Run integration tests
uv run tests/test_app_flow.py

# Run MCP connectivity tests
uv run tests/simple_mcp_test.py

# Run diagnostic tests
uv run tests/diagnostic_mcp.py
```

## Troubleshooting

### **Common Issues**

1. **"Orchestrator not ready"**: Wait for startup to complete (~10 seconds)
2. **MCP connection errors**: Check that database file exists and is readable
3. **SQL validation failures**: Check for unsafe operations (DROP, DELETE without WHERE)

### **Debug Tools**

- **Health Check**: `GET /api/health` endpoint shows system status
- **MCP Diagnostics**: Run diagnostic scripts to test MCP servers independently
- **Browser Console**: Check for JavaScript errors in browser dev tools

## Why This Works Better Than Streamlit

| Feature | FastAPI Solution | Streamlit Issues |
|---------|------------------|------------------|
| **Async Handling** | ✅ Native async support | ❌ Event loop conflicts |
| **State Management** | ✅ Clean API requests | ❌ Session state corruption |
| **Performance** | ✅ Concurrent requests | ❌ Single-threaded reruns |
| **Debugging** | ✅ Clear error handling | ❌ Async debugging nightmare |
| **Scalability** | ✅ Production-ready | ❌ Demo/prototype only |

## Contributing

This is a sophisticated demonstration of modern AI application architecture. The codebase showcases:

- **Clean Architecture**: Separation of concerns with clear interfaces
- **Modern Python**: Type hints, async/await, dataclasses
- **Professional Patterns**: Dependency injection, protocol-based design
- **Production Ready**: Health checks, error handling, logging

## License

This project demonstrates advanced AI agent orchestration and MCP integration patterns.

---

**Ready to explore your music database with AI? Start the app and ask away!**