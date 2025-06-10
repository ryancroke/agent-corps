# Tests

This directory contains test files for the A2A MCP SQL Chat project.

## Test Files

- `test_app_flow.py` - Integration tests that mimic actual application flow
- `simple_mcp_test.py` - Simple MCP server connectivity tests
- `diagnostic_mcp.py` - Detailed diagnostic tool for MCP server debugging

## Running Tests

```bash
# Run integration tests
uv run tests/test_app_flow.py

# Run simple MCP tests
uv run tests/simple_mcp_test.py

# Run diagnostic tests
uv run tests/diagnostic_mcp.py
```

## Test Categories

- **Integration Tests**: Test the complete orchestrator workflow
- **Unit Tests**: Test individual MCP server connections
- **Diagnostic Tests**: Debug MCP server health and performance