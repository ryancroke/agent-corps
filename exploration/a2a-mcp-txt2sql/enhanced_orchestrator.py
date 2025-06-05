"""
Enhanced orchestrator with A2A SQL validation.
"""

import asyncio
import json
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from mcp_servers.sqlite_interface import SQLiteMCP
from agents.sql_validation_agent import SQLValidationAgent


class State(TypedDict):
    user_query: str
    needs_sql: bool
    sql_query: str
    is_valid: bool
    validation_result: dict
    sql_result: str
    final_response: str


class EnhancedSQLOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.sqlite_mcp = SQLiteMCP()
        self.validator = SQLValidationAgent()
        self.graph = None
    
    async def initialize(self):
        """Initialize all components."""
        await self.sqlite_mcp.initialize()
        await self.validator.initialize()
        self.graph = self._build_graph()
        print("✓ Enhanced SQL Orchestrator initialized")
    
    def _build_graph(self):
        """Build LangGraph with A2A validation."""
        graph = StateGraph(State)
        
        graph.add_node("route", self._route_query)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_sql", self._execute_sql)
        graph.add_node("direct_response", self._direct_response)
        
        graph.set_entry_point("route")
        
        # Routing logic
        graph.add_conditional_edges(
            "route",
            lambda state: "generate_sql" if state["needs_sql"] else "direct_response"
        )
        
        graph.add_edge("generate_sql", "validate_sql")
        
        # Validation routing
        graph.add_conditional_edges(
            "validate_sql",
            lambda state: "execute_sql" if state["is_valid"] else "direct_response"
        )
        
        graph.add_edge("execute_sql", END)
        graph.add_edge("direct_response", END)
        
        return graph.compile()
    
    async def _route_query(self, state: State) -> State:
        """Decide if query needs SQL."""
        prompt = f"Does this query need database access? Answer only 'yes' or 'no': {state['user_query']}"
        response = await self.llm.ainvoke(prompt)
        needs_sql = "yes" in response.content.lower()
        return {**state, "needs_sql": needs_sql}
    
    async def _generate_sql(self, state: State) -> State:
        """Generate SQL query."""
        prompt = f"""Convert to SQL for Chinook music database: {state['user_query']}

Return ONLY the SQL query with no formatting, no code blocks, no explanation.
Example: SELECT COUNT(*) FROM Artist"""
        
        response = await self.llm.ainvoke(prompt)
        sql_query = response.content.strip()
        
        # Clean up any markdown formatting
        if sql_query.startswith("```"):
            lines = sql_query.split("\n")
            sql_query = "\n".join(line for line in lines if not line.startswith("```") and line.strip())
            sql_query = sql_query.strip()
        
        return {**state, "sql_query": sql_query}
    
    async def _validate_sql(self, state: State) -> State:
        """Validate SQL using A2A agent."""
        # Create A2A message
        a2a_message = {
            "task": {
                "skill": "validate_sql",
                "parameters": {
                    "sql": state["sql_query"]
                }
            }
        }
        
        # Send to validation agent
        result = await self.validator.process_a2a_message(a2a_message)
        
        if result["status"] == "completed":
            validation_result = result["artifacts"][0]
            is_valid = validation_result["is_valid"] and validation_result["safe"]
        else:
            validation_result = {"is_valid": False, "issues": ["Validation failed"], "safe": False}
            is_valid = False
        
        return {**state, "is_valid": is_valid, "validation_result": validation_result}
    
    async def _execute_sql(self, state: State) -> State:
        """Execute validated SQL."""
        result = await self.sqlite_mcp.query(f"Execute: {state['sql_query']}")
        return {**state, "sql_result": result, "final_response": result}
    
    async def _direct_response(self, state: State) -> State:
        """Handle non-SQL or invalid SQL."""
        if not state["needs_sql"]:
            response = await self.llm.ainvoke(state['user_query'])
            return {**state, "final_response": response.content}
        else:
            # SQL was invalid
            issues = state.get("validation_result", {}).get("issues", ["Unknown validation error"])
            error_msg = f"SQL validation failed: {', '.join(issues)}"
            return {**state, "final_response": error_msg}
    
    async def run(self, user_query: str) -> str:
        """Process query through enhanced workflow."""
        initial_state = {
            "user_query": user_query,
            "needs_sql": False,
            "sql_query": "",
            "is_valid": False,
            "validation_result": {},
            "sql_result": "",
            "final_response": ""
        }
        
        result = await self.graph.ainvoke(initial_state)
        return result["final_response"]
    
    async def close(self):
        """Clean up resources."""
        await self.sqlite_mcp.close()


# Test function
async def test():
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()
    
    # Test valid SQL query
    result = await orchestrator.run("How many artists are in the database?")
    print(f"Valid query result: {result[:100]}...")
    
    # Test dangerous SQL
    result = await orchestrator.run("DROP TABLE Artist")
    print(f"Dangerous query result: {result}")
    
    # Test non-SQL query
    result = await orchestrator.run("What is Python?")
    print(f"Non-SQL result: {result[:100]}...")
    
    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(test())