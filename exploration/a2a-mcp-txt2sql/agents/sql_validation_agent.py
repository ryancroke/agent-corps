"""
SQL Validation Agent using Python REPL MCP server.
Uses the Pydantic AI approach for MCP connection.
"""

import asyncio
import json
from typing import Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class SQLValidationAgent:
    def __init__(self):
        self.agent_id = "sql-validator-001"
        self.server_params = StdioServerParameters(
            command='deno',
            args=[
                'run', '-N', '-R=node_modules', '-W=node_modules',
                '--node-modules-dir=auto',
                'jsr:@pydantic/mcp-run-python', 'stdio'
            ]
        )
        
    async def initialize(self):
        """Initialize (no persistent connection)."""
        print("✓ SQL Validation Agent initialized")
    
    def get_agent_card(self) -> Dict[str, Any]:
        """Return A2A Agent Card."""
        return {
            "id": self.agent_id,
            "name": "SQL Validation Agent",
            "description": "Validates SQL queries using Python REPL MCP",
            "version": "1.0.0",
            "skills": [
                {
                    "name": "validate_sql",
                    "description": "Validate SQL query syntax and safety",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "SQL query to validate"}
                        },
                        "required": ["sql"]
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "is_valid": {"type": "boolean"},
                            "issues": {"type": "array", "items": {"type": "string"}},
                            "safe": {"type": "boolean"}
                        }
                    }
                }
            ]
        }
    
    async def validate_sql(self, sql: str) -> Dict[str, Any]:
        """Validate SQL using Python REPL MCP."""
        
        validation_code = f'''
# /// script
# dependencies = ["sqlglot"]
# ///
import sqlglot

sql = """{sql}"""
issues = []
is_valid = True
safe = True

try:
    parsed = sqlglot.parse_one(sql)
    
    # Check for dangerous operations
    if parsed.find(sqlglot.expressions.Drop):
        issues.append("Contains DROP statement")
        safe = False
    
    if parsed.find(sqlglot.expressions.Delete):
        issues.append("Contains DELETE statement") 
        safe = False
        
    if not isinstance(parsed, sqlglot.expressions.Select):
        issues.append("Query is not a SELECT statement")
        safe = False
        
except Exception as e:
    is_valid = False
    issues.append(f"SQL error: {{str(e)}}")
    safe = False

result = {{"is_valid": is_valid and len(issues) == 0, "issues": issues, "safe": safe}}
print("VALIDATION_RESULT:", result)
result
'''
        
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool('run_python_code', {'python_code': validation_code})
                    
                    # Debug: print the raw output
                    output = result.content[0].text
                    print(f"DEBUG - MCP Output: {output}")
                    
                    # Parse the result from MCP output
                    if "VALIDATION_RESULT:" in output:
                        # Extract the dict after "VALIDATION_RESULT:"
                        result_line = output.split("VALIDATION_RESULT:")[1].strip()
                        print(f"DEBUG - Result line: {result_line}")
                        
                        if "'is_valid': True" in result_line:
                            return {"is_valid": True, "issues": [], "safe": True}
                        else:
                            return {"is_valid": False, "issues": ["Validation failed"], "safe": False}
                    else:
                        print(f"DEBUG - No VALIDATION_RESULT found in output")
                        return {"is_valid": False, "issues": ["Could not parse result"], "safe": False}
                        
        except Exception as e:
            print(f"DEBUG - Exception in validate_sql: {e}")
            return {"is_valid": False, "issues": [f"MCP error: {str(e)}"], "safe": False}
    
    async def process_a2a_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process A2A task message."""
        task_type = message.get("task", {}).get("skill")
        
        if task_type == "validate_sql":
            sql = message.get("task", {}).get("parameters", {}).get("sql")
            result = await self.validate_sql(sql)
            
            return {
                "status": "completed",
                "artifacts": [result]
            }
        
        return {"status": "failed", "error": "Unknown task"}


# Test function
async def test_agent():
    agent = SQLValidationAgent()
    await agent.initialize()
    
    # Test validation
    result = await agent.validate_sql("SELECT * FROM users WHERE id = 1")
    print(f"Validation result: {result}")


if __name__ == "__main__":
    asyncio.run(test_agent())