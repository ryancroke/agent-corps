"""
Simple LangGraph orchestrator for text-to-SQL workflow.
"""

import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from mcp_servers.sqlite_interface import SQLiteMCP

load_dotenv()

class State(TypedDict):
    user_query: str
    needs_sql: bool
    sql_query: str
    sql_result: str
    final_response: str


class SQLOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.sqlite_mcp = SQLiteMCP()
        self.graph = None
    
    async def initialize(self):
        """Initialize MCP and build graph."""
        await self.sqlite_mcp.initialize()
        self.graph = self._build_graph()
        print("✓ SQL Orchestrator initialized")
    
    def _build_graph(self):
        """Build the LangGraph workflow."""
        graph = StateGraph(State)
        
        graph.add_node("route", self._route_query)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("execute_sql", self._execute_sql)
        graph.add_node("direct_response", self._direct_response)
        
        graph.set_entry_point("route")
        
        # Conditional routing
        graph.add_conditional_edges(
            "route",
            lambda state: "generate_sql" if state["needs_sql"] else "direct_response"
        )
        
        graph.add_edge("generate_sql", "execute_sql")
        graph.add_edge("execute_sql", END)
        graph.add_edge("direct_response", END)
        
        return graph.compile()
    
    async def _route_query(self, state: State) -> State:
        """Decide if query needs SQL or can be answered directly."""
        prompt = f"""
        User query: {state['user_query']}
        
        Does this query require accessing the database? 
        Answer only 'yes' or 'no'.
        """
        
        response = await self.llm.ainvoke(prompt)
        needs_sql = "yes" in response.content.lower()
        
        return {**state, "needs_sql": needs_sql}
    
    async def _generate_sql(self, state: State) -> State:
        """Generate SQL query."""
        prompt = f"""
        Convert this natural language query to SQL for a music database:
        {state['user_query']}
        
        Return only the SQL query, no explanation.
        """
        
        response = await self.llm.ainvoke(prompt)
        sql_query = response.content.strip()
        
        return {**state, "sql_query": sql_query}
    
    async def _execute_sql(self, state: State) -> State:
        """Execute SQL using MCP."""
        result = await self.sqlite_mcp.query(f"Execute this SQL: {state['sql_query']}")
        return {**state, "sql_result": result, "final_response": result}
    
    async def _direct_response(self, state: State) -> State:
        """Handle non-SQL queries."""
        response = await self.llm.ainvoke(state['user_query'])
        return {**state, "final_response": response.content}
    
    async def run(self, user_query: str) -> str:
        """Process user query through the workflow."""
        if not self.graph:
            raise RuntimeError("Call initialize() first")
        
        initial_state = {
            "user_query": user_query,
            "needs_sql": False,
            "sql_query": "",
            "sql_result": "",
            "final_response": ""
        }
        
        result = await self.graph.ainvoke(initial_state)
        return result["final_response"]
    
    async def close(self):
        """Clean up resources."""
        await self.sqlite_mcp.close()


# Example usage
async def test():
    orchestrator = SQLOrchestrator()
    await orchestrator.initialize()
    
    # Test SQL query
    result = await orchestrator.run("How many artists are in the database?")
    print(f"SQL Result: {result}")
    
    # Test non-SQL query
    result = await orchestrator.run("What is the capital of France?")
    print(f"Direct Result: {result}")
    
    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(test())