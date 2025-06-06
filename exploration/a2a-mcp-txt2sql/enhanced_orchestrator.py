"""
Enhanced orchestrator with A2A SQL validation.
"""

import asyncio
from datetime import datetime
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.sql_validation_agent import SQLValidationAgent
from mcp_servers.chroma_interface import ChromaMCP
from mcp_servers.sqlite_interface import SQLiteMCP


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    needs_sql: bool
    sql_query: str
    is_valid: bool
    validation_result: dict
    sql_result: str
    final_response: str
    mcp_servers_used: list[str]
    agents_used: list[str]


class EnhancedSQLOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.sqlite_mcp = SQLiteMCP()
        self.validator = SQLValidationAgent()
        self.chroma_logger = ChromaMCP()
        self.checkpointer = InMemorySaver()
        self.graph = None

    async def initialize(self):
        """Initialize all components."""
        await self.sqlite_mcp.initialize()
        await self.validator.initialize()
        await self.chroma_logger.initialize()
        self.graph = self._build_graph()
        print("✓ Enhanced SQL Orchestrator initialized")

    def _build_graph(self):
        """Build LangGraph with A2A validation."""
        graph = StateGraph(State)

        graph.add_node("initialize_state", self._initialize_state)
        graph.add_node("contextualize", self._contextualize_query)
        graph.add_node("route", self._route_query)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_sql", self._execute_sql)
        graph.add_node("direct_response", self._direct_response)

        graph.set_entry_point("contextualize")
        graph.add_edge("contextualize", "initialize_state")
        graph.add_edge("initialize_state", "route")

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

        return graph.compile(checkpointer=self.checkpointer)

    async def _route_query(self, state: State) -> State:
        """Decide if query needs SQL."""
        prompt = f"Does this query need database access? Answer only 'yes' or 'no': {state['user_query']}"
        response = await self.llm.ainvoke(prompt)
        needs_sql = "yes" in response.content.lower()
        print(f"✓ Query needs SQL: {needs_sql}")
        return {**state, "needs_sql": needs_sql}

    async def _contextualize_query(self, state: State) -> State:
        """Rewrite the user's query using the message history from the state."""
        # The last message is the current user query
        user_query = state["messages"][-1].content

        # If it's the start of a conversation, no context needed
        if len(state["messages"]) <= 1:
            return {"standalone_query": user_query}

        # Use the contextualizer logic (can be in a separate file)
        # Note: We need to adapt the `contextualize_query` function slightly
        # to not require the `last_turn_state` as a separate object, but we can
        # derive it from the message history if needed. For now, a simpler
        # approach is to just use the message history.

        context_prompt = f"""Based on the chat history, rewrite the following user query to be a standalone question.

        History:
        {state['messages']}

        User Query: {user_query}

        Standalone Query:"""

        response = await self.llm.ainvoke(context_prompt)
        rewritten_query = response.content.strip()
        print(f"✓ Contextualized query: {rewritten_query}")

        return {"standalone_query": rewritten_query}

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

        agents_used = state.get("agents_used", []) + ["sql_generator_llm"]

        return {**state, "sql_query": sql_query, "agents_used": agents_used}

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

        agents_used = state.get("agents_used", []) + ["sql_validation_agent"]
        mcp_servers_used = state.get("mcp_servers_used", []) + ["python_repl_mcp"]

        return {
        **state,
        "is_valid": is_valid,
        "validation_result": validation_result,
        "agents_used": agents_used,
        "mcp_servers_used": mcp_servers_used
        }

    async def _execute_sql(self, state: State) -> State:
        """Execute validated SQL."""
        result = await self.sqlite_mcp.query(f"Execute: {state['sql_query']}")
        mcp_servers_used = state.get("mcp_servers_used", []) + ["sqlite_mcp"]

        return {
            **state,
            "sql_result": result,
            "final_response": result,
            "mcp_servers_used": mcp_servers_used
        }

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


    async def _log_interaction(self, final_state: State):
        """Logs the complete interaction details to ChromaDB."""
        # We use .get() for optional fields to avoid KeyErrors
        mcp_used = final_state.get("mcp_servers_used", [])
        agents_used = final_state.get("agents_used", [])

        interaction_details = {
            "user_query": final_state.get("user_query"),
            "response": final_state.get("final_response"),
            "mcp_servers_used": mcp_used,
            "agents_used": agents_used,
            "sql_generated": final_state.get("sql_query"),
            "validation_result": final_state.get("validation_result"),
            'timestamp': datetime.now().isoformat()

            # Add any other relevant details from the state
        }


        try:
            await self.chroma_logger.add_log(interaction_details)
            print("✓ Interaction logged to ChromaDB")
        except Exception as e:
            # Never let logging failures crash the main application
            print(f"✗ Failed to log interaction to ChromaDB: {e}")

    async def _initialize_state(self, state: State) -> State:
        """
        Initializes custom state fields if they don't exist.
        This is crucial for the first run of a new conversation thread.
        """
        # These are the keys that are not part of the initial 'messages' input
        # but are required by downstream nodes.
        required_keys = {
            "standalone_query": "",
            "needs_sql": False,
            "sql_query": "",
            "is_valid": False,
            "validation_result": {},
            "sql_result": "",
            "final_response": "",
            "mcp_servers_used": [],
            "agents_used": []
        }

        # We can't just return the whole state, we need to return a dict
        # of the keys to update.
        updates = {}
        for key, default_value in required_keys.items():
            if key not in state or state[key] is None:
                updates[key] = default_value

        # Also add the original user query for logging purposes
        updates["user_query"] = state["messages"][-1].content

        return updates

    async def run(self, user_query: str, thread_id: str) -> State:
        """Process query through enhanced workflow."""

        inputs = {"messages": [("user", user_query)]}
        config = {"configurable": {"thread_id": thread_id}}

        final_state = await self.graph.ainvoke(inputs, config)
        await self._log_interaction(final_state)
        return final_state

    async def close(self):
        """Clean up resources."""
        await self.sqlite_mcp.close()
        await self.chroma_logger.close()


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
