# Multi-Agent Architecture: LangGraph Supervisor + A2A + MCP Integration

## Overview

This document outlines a scalable multi-agent architecture that integrates three key technologies using LangGraph's supervisor pattern:
- **LangGraph Supervisor**: Intelligent orchestration and agent handoff management
- **A2A Protocol**: Agent-to-agent collaboration and capability discovery
- **MCP Servers**: Direct infrastructure and tool access

## Core Architecture Concepts

### Three Distinct Agent Types

**MCP Agents (Infrastructure Layer)**:
- SQLiteMCP, ChromaMCP - **resource providers**
- Stateless, focused on specific capabilities
- Optimized for performance and direct access
- Handle low-level operations: database queries, file access, API calls

**A2A Agents (Business Logic Layer)**:
- SQLValidationAgent, EmailComposerAgent - **decision-making agents**
- Stateful interactions with context and negotiation
- Handle complex workflows and business intelligence
- Can internally coordinate multiple MCP servers

**LangGraph Supervisor (Orchestration Layer)**:
- Supervisor agent that intelligently routes tasks to specialized agents
- Uses built-in handoff tools for clean agent delegation
- Handles conversation state and message history management
- Automatically routes between A2A agents and direct MCP access
- Provides task-specific context to each agent

## Architectural Layers

```
┌─────────────────────────────────────────────────┐
│            FastAPI + WebSocket                  │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│          LangGraph Supervisor                   │
│        (Intelligent Routing Agent)              │
└─────┬─────────────┬─────────────┬───────────────┘
      │             │             │
┌─────▼──────┐ ┌────▼────────┐ ┌──▼──────────────┐
│ SQLite     │ │ A2A Agents  │ │ Email Composer  │
│ Agent      │ │ (SQL Valid) │ │ A2A Agent       │
│ (Direct    │ │             │ │                 │
│ MCP)       │ │             │ │                 │
└─────┬──────┘ └────┬────────┘ └──┬──────────────┘
      │             │             │
┌─────▼─────────────▼─────────────▼───────────────┐
│              MCP Servers                        │
│    (SQLite, Chroma, Email APIs)                │
└─────────────────────────────────────────────────┘
```

## Integration Patterns

### Pattern 1: A2A Agent Wraps MCP Servers

```python
class SQLAnalysisA2AAgent:
    def __init__(self):
        self.mcp_sqlite = SQLiteMCP()  # MCP server for raw data access
        self.mcp_visualization = ChartMCP()  # MCP server for chart generation
        
    def get_agent_card(self):
        return {
            "id": "sql-analyst-v1",
            "capabilities": [
                {
                    "skill": "sales_trend_analysis",
                    "description": "Analyze sales trends and create visualizations"
                }
            ]
        }
    
    async def execute_task(self, task):
        # High-level A2A task execution
        if task.skill == "sales_trend_analysis":
            # Use MCP servers as internal tools
            data = await self.mcp_sqlite.query("SELECT * FROM sales...")
            chart = await self.mcp_visualization.create_chart(data)
            
            return A2AArtifact(
                type="analysis_report",
                content={"data": data, "visualization": chart}
            )
```

### Pattern 2: LangGraph Supervisor with Hybrid Handoffs

```python
class HybridSupervisorOrchestrator:
    def __init__(self):
        # MCP servers for direct access
        self.sqlite_mcp = SQLiteMCP()
        self.chroma_mcp = ChromaMCP()
        
        # A2A agents as LangGraph agents
        self.sql_validation_agent = create_react_agent(...)
        self.email_composer_agent = create_react_agent(...)
        
        # Direct MCP wrapper agents
        self.sqlite_agent = create_react_agent(
            tools=[self.create_mcp_tools(self.sqlite_mcp)],
            prompt="You handle direct database queries efficiently."
        )
        
        # Build supervisor with hybrid routing
        self.supervisor = self._build_hybrid_supervisor()
```

## LangGraph Supervisor Architecture

### Hybrid Handoff Tools

```python
def create_hybrid_handoff_tools(self):
    # A2A agent handoffs for complex workflows
    transfer_to_sql_validator = create_handoff_tool(
        agent_name="sql_validation_agent",
        description="Validate SQL queries for safety and correctness"
    )
    
    transfer_to_email_composer = create_handoff_tool(
        agent_name="email_composer_agent", 
        description="Compose and send professional emails"
    )
    
    # Direct MCP handoffs for simple operations
    transfer_to_sqlite = create_handoff_tool(
        agent_name="sqlite_agent",
        description="Execute simple database queries directly"
    )
    
    return [transfer_to_sql_validator, transfer_to_email_composer, transfer_to_sqlite]
```

### Intelligent Supervisor Agent

```python
supervisor_agent = create_react_agent(
    model="gpt-4",
    tools=self.create_hybrid_handoff_tools(),
    prompt="""
    You are a supervisor managing both A2A agents and direct MCP access.
    
    For SIMPLE data queries → use sqlite_agent (direct MCP)
    For COMPLEX workflows → use A2A agents (sql_validation_agent, email_composer_agent)
    
    Examples:
    - "How many artists?" → sqlite_agent
    - "Validate this SQL: DROP TABLE users" → sql_validation_agent  
    - "Find jazz sales and email report" → sql_validation_agent + email_composer_agent
    
    Always choose the most efficient path based on query complexity.
    """,
    name="supervisor"
)
```

### Hybrid Supervisor Graph Structure

```python
def _build_hybrid_supervisor(self):
    graph = StateGraph(MessagesState)
    
    # Supervisor with intelligent routing
    graph.add_node(
        self.supervisor_agent,
        destinations=("sqlite_agent", "sql_validation_agent", "email_composer_agent")
    )
    
    # Direct MCP agents (fast path)
    graph.add_node(self.sqlite_agent)
    
    # A2A agents (intelligent path) 
    graph.add_node(self.sql_validation_agent)
    graph.add_node(self.email_composer_agent)
    
    # All agents return to supervisor
    graph.add_edge(START, "supervisor")
    graph.add_edge("sqlite_agent", "supervisor") 
    graph.add_edge("sql_validation_agent", "supervisor")
    graph.add_edge("email_composer_agent", "supervisor")
    
    return graph.compile()
```

### Task Delegation with Context

```python
# Using task description handoffs for precise agent instructions
def create_task_description_handoff_tool(*, agent_name: str, description: str):
    @tool(name=f"transfer_to_{agent_name}", description=description)
    def handoff_tool(
        task_description: Annotated[str, "Specific task for the agent"],
        state: Annotated[MessagesState, InjectedState],
    ) -> Command:
        task_message = {"role": "user", "content": task_description}
        agent_input = {**state, "messages": [task_message]}
        return Command(goto=[Send(agent_name, agent_input)], graph=Command.PARENT)
    return handoff_tool

# Supervisor creates specific, contextual tasks
supervisor_prompt = """
Examples of task delegation:
- Simple: "How many artists?" → sqlite_agent: "Execute: SELECT COUNT(*) FROM Artist"  
- Complex: "Validate SQL" → sql_validation_agent: "Check this SQL for safety: DROP TABLE users"
- Workflow: "Sales report" → sql_validation_agent: "Find jazz sales data" → email_composer_agent: "Email results to marketing"
"""
```

## Supervisor Intelligence & Routing

### Built-in LLM Routing Decision Making

The supervisor's LLM automatically analyzes queries and chooses the optimal agent path:

```python
# The supervisor LLM intelligently routes based on its prompt
supervisor_routing_examples = {
    "How many artists?": "sqlite_agent (direct MCP - fast)",
    "Validate: DROP TABLE users": "sql_validation_agent (A2A - safety critical)", 
    "Find jazz sales and email report": "sql_validation_agent → email_composer_agent (multi-step A2A workflow)",
    "Explain the top artists": "sqlite_agent → explanation via supervisor synthesis"
}
```

### Supervisor Routing Examples

**Simple Direct MCP**: "How many artists are in the database?"
```python
# Supervisor transfers to sqlite_agent with specific task
supervisor → transfer_to_sqlite_agent("Execute: SELECT COUNT(*) FROM Artist") 
→ sqlite_agent executes via direct MCP 
→ returns to supervisor with result
```

**Complex A2A Workflow**: "Validate this SQL and email safety report"
```python
# Supervisor orchestrates multi-agent workflow
supervisor → transfer_to_sql_validator("Check: DROP TABLE users for safety")
→ sql_validation_agent (A2A) validates and returns result
→ supervisor → transfer_to_email_composer("Email security alert about dangerous SQL attempt")
→ email_composer_agent (A2A) sends notification
→ returns to supervisor with completion status
```

**Hybrid Multi-step**: "Find top jazz artists and explain the business impact"
```python
# Supervisor coordinates MCP + reasoning
supervisor → transfer_to_sqlite_agent("Get top 10 jazz artists by sales")
→ sqlite_agent returns raw data
→ supervisor synthesizes explanation using LLM capabilities
→ returns comprehensive business analysis
```

## A2A Integration as LangGraph Agents

### A2A Agents as Standard LangGraph Nodes

A2A agents are integrated as standard LangGraph agents that can be called via handoff tools:

```python
# A2A agents become LangGraph agents
sql_validation_agent = create_react_agent(
    model="gpt-4",
    tools=[PythonREPLMCP()],  # A2A agent uses MCP tools internally
    prompt="""
    You are an A2A SQL validation agent.
    Use Python REPL MCP to validate SQL queries for safety.
    Check for: DROP, DELETE, UPDATE, dangerous patterns.
    Return: {"is_valid": bool, "issues": [str], "safe": bool}
    """,
    name="sql_validation_agent"
)

email_composer_agent = create_react_agent(
    model="gpt-4", 
    tools=[EmailMCP(), TemplateMCP()],  # A2A agent coordinates multiple MCPs
    prompt="""
    You are an A2A email composition agent.
    Create professional emails, use templates, send notifications.
    Handle: business reports, alerts, summaries, notifications.
    """,
    name="email_composer_agent"
)
```

### A2A Agent Cards Integration

```python
# A2A agents can still provide Agent Cards for external discovery
class SQLValidationA2AAgent:
    def get_agent_card(self):
        return {
            "id": "sql-validator-langgraph-v1",
            "capabilities": [
                {
                    "skill": "validate_sql_query",
                    "description": "Validate SQL queries for safety and syntax",
                    "integration": "langgraph_handoff"  # Indicates LangGraph integration
                }
            ]
        }
    
    # Can be called via LangGraph handoff OR A2A protocol
    async def handle_a2a_request(self, task):
        # Bridge A2A calls to LangGraph execution
        return await self.langgraph_agent.invoke({"messages": [task.to_message()]})
```

## FastAPI Integration

### WebSocket-based Real-time Communication

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()

# Serve static files (HTML/CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    orchestrator = LangGraphOrchestrator()
    await orchestrator.initialize()
    
    try:
        while True:
            # Receive user message
            data = await websocket.receive_json()
            user_query = data["message"]
            
            # Process through LangGraph with streaming updates
            async for update in orchestrator.stream_response(user_query, session_id):
                await websocket.send_json({
                    "type": update.type,  # "progress", "result", "error"
                    "content": update.content,
                    "metadata": update.metadata
                })
                
    except WebSocketDisconnect:
        await orchestrator.cleanup(session_id)
```

### Supervisor Streaming Support

```python
class HybridSupervisorOrchestrator:
    async def stream_response(self, query: str, session_id: str):
        """Stream LangGraph supervisor execution with real-time updates"""
        config = {"configurable": {"thread_id": session_id}}
        
        async for event in self.supervisor.astream(
            {"messages": [("user", query)]}, 
            config=config
        ):
            # Stream supervisor decisions and agent handoffs
            if "supervisor" in event:
                yield StreamUpdate(
                    type="supervisor_thinking", 
                    content="Analyzing query and selecting optimal agent...",
                    metadata={"supervisor_state": "routing"}
                )
            
            elif "sqlite_agent" in event:
                yield StreamUpdate(
                    type="mcp_execution",
                    content="Executing direct database query...",
                    metadata={"agent_type": "direct_mcp", "agent": "sqlite"}
                )
            
            elif "sql_validation_agent" in event:
                yield StreamUpdate(
                    type="a2a_execution",
                    content="Validating SQL query for safety...",
                    metadata={"agent_type": "a2a_agent", "agent": "sql_validator"}
                )
            
            elif "email_composer_agent" in event:
                yield StreamUpdate(
                    type="a2a_execution", 
                    content="Composing and sending email...",
                    metadata={"agent_type": "a2a_agent", "agent": "email_composer"}
                )
```

## Key Design Principles

1. **Supervisor Intelligence**: LangGraph supervisor LLM automatically routes to optimal agents
2. **Clean Handoffs**: Built-in transfer tools eliminate custom routing logic
3. **Hybrid Efficiency**: Direct MCP for simple ops, A2A agents for complex workflows
4. **Automatic Return Flow**: All agents return to supervisor for coordination
5. **Task-Specific Context**: Each agent receives precisely what it needs via task delegation
6. **Protocol Agnostic**: A2A agents work as LangGraph nodes while maintaining A2A compatibility
7. **Conversational Memory**: Supervisor maintains conversation state across all agent interactions
8. **Real-time Streaming**: Live updates show supervisor decisions and agent execution

## Benefits of Supervisor Architecture

- **Automatic Intelligence**: Supervisor LLM learns optimal routing patterns
- **Clean Integration**: A2A agents work seamlessly as LangGraph nodes
- **No Custom Logic**: Built-in handoff tools replace manual routing code
- **Efficient Execution**: Direct path for simple operations, intelligent path for complex workflows
- **Scalable Growth**: New agents automatically available via handoff tools
- **Conversation Continuity**: Supervisor maintains context across all agent interactions
- **Real-time Visibility**: Stream supervisor decisions and agent execution live
- **Protocol Flexibility**: Agents can be called via LangGraph handoffs OR external A2A protocol
- **Task Precision**: Each agent gets exactly the context and instructions it needs

## Role Definitions

### LangGraph Supervisor Role
- Intelligent LLM-based routing to optimal agents
- Built-in handoff management via transfer tools
- Conversation memory and context preservation
- Task-specific delegation with precise instructions
- Automatic agent return flow coordination
- Real-time execution streaming
- Fallback and error recovery orchestration

### A2A Agents (as LangGraph Nodes)
- Complex business logic and multi-step reasoning
- Internal coordination of multiple MCP servers
- Stateful interactions with context preservation
- Can maintain A2A protocol compatibility for external calls
- Handle domain-specific intelligence (validation, composition, analysis)
- Generate structured artifacts and results

### MCP Servers Handle
- Direct infrastructure access (databases, APIs, files)
- High-performance, stateless operations
- Low-level tool primitives
- Resource management and connections
- Factory pattern creation for consistent interfaces

### FastAPI Frontend Handles
- WebSocket-based real-time communication
- Static file serving (HTML/CSS/JS)
- Session management and authentication
- Real-time progress updates during execution
- Responsive user interface without blocking

## Summary

The architecture leverages LangGraph's supervisor pattern for intelligent multi-agent orchestration: **The supervisor LLM automatically routes queries to the optimal combination of A2A agents (for complex workflows) and direct MCP access (for simple operations), using built-in handoff tools for clean agent delegation.** 

Key innovations:
- **No Custom Routing**: Supervisor LLM handles all routing decisions
- **Hybrid Agent Integration**: A2A agents work as LangGraph nodes while maintaining protocol compatibility  
- **Automatic Optimization**: System learns optimal routing patterns over time
- **Real-time Transparency**: Live streaming of supervisor decisions and agent execution
- **Seamless Scalability**: New agents automatically integrate via handoff tools

This creates a self-improving, intelligent multi-agent system that efficiently handles everything from simple database queries to complex multi-step business workflows with full conversation continuity and real-time user feedback.

Of course. This is a pivotal concept, and capturing it clearly is essential for your project's architecture. The idea of using MCP `Prompts` as first-class citizens is what separates a basic agent framework from a truly scalable and intelligent one.

Here is a detailed Markdown document that encapsulates our conversation, analyzes the video's argument, and provides a concrete plan for your system.

---

# Architectural Plan: Leveraging MCP Prompts for Agentic Discovery and Workflow Composition

## 1. Executive Summary

This document outlines a "Prompt-first" architectural strategy for our intelligent platform. Traditional agent design often stops at defining a collection of **Tools**, leaving the agent's LLM to perform the complex and error-prone task of discovering and sequencing these tools.

As argued by the creator of the `quick-data-mcp` server, this approach is limited. The most powerful and underutilized primitive in the Model Context Protocol (MCP) is the **Prompt**.

We will architect our system around the principle that **Prompts are not just text templates; they are high-level, composable, and self-documenting agentic workflows.** By embracing this, we will simplify our core orchestration logic, increase system robustness, and build agents that are dramatically more capable and efficient.

## 2. The Core Problem: The Agent's "Cold Start"

An agent, no matter how intelligent its base LLM, is not omniscient. When our platform's `Orchestrator Agent` needs to delegate a task to a specialized MCP server (e.g., for data analysis, CRM interaction, or GitHub management), it faces a critical challenge:

*   **How do I know what this server can do?**
*   **Of the 30+ tools available, which ones do I need to call?**
*   **In what sequence should I call them?**

Relying on the agent to infer this from a flat list of tool names and descriptions is brittle and requires extensive, hard-coded knowledge or complex runtime planning. As demonstrated in the video, this often forces the developer or the agent to rely on external documentation (`README.md`), which defeats the purpose of a dynamic, programmatic interface.

## 3. The MCP Primitive Tier List: A Shift in Perspective

The author's central argument is that the three MCP primitives exist in a hierarchy of leverage. Most developers stop at the B-Tier, missing the S-Tier where true agentic power lies.

> **Prompts (S-Tier) > Tools (A-Tier) > Resources (B-Tier)**

| Tier | Primitive | Role | Description |
| :--- | :--- | :--- | :--- |
| **B-Tier** | **Resources** | Raw Materials | The underlying data. A file URI, a database table, a raw API response. Essential, but inert on its own. |
| **A-Tier** | **Tools** | Atomic Actions | A single, discrete function that operates on a resource (e.g., `load_dataset`, `create_chart`, `get_dataset_info`). They are the verbs of the system. |
| **S-Tier** | **Prompts** | **Agentic Workflows** | A high-level, named capability that **composes a sequence of tool calls and resource access**. It's a pre-built, repeatable recipe for solving a specific, domain-relevant problem. |

By focusing on `Prompts`, we shift complexity *out* of our central agent's brain and *into* the specialized MCP servers where it belongs.

## 4. The Three Key Advantages of a Prompt-First Strategy

### 4.1. Solving Discovery and the "Cold Start" Problem
A well-designed MCP server should use a `Prompt` to teach agents how to use it.

*   **Tool-Only Approach:** The agent connects and asks, "What are your tools?" It gets back a list of 50 functions and is overwhelmed.
*   **Prompt-Driven Approach:** The agent connects and invokes a single discovery prompt, like `/quick-data:list_mcp_assets_prompt`. The server responds with a rich, natural-language summary that includes:
    *   A high-level overview of its purpose.
    *   A categorized list of its most important `Prompts` (e.g., "Data Exploration Prompts", "Analysis Workflow Prompts").
    *   A "Quick Start Flow" that gives the agent a clear, step-by-step guide on how to begin.

### 4.2. Composing Atomic Tools into Intelligent Workflows
`Prompts` turn multi-step, fragile tool chains into single, robust commands.

*   **Tool-Only Approach:** To get business insights, our agent would need to: 1. `load_dataset`, 2. `get_dataset_info`, 3. `find_correlations`, 4. `suggest_analysis`, 5. `create_chart`, hoping it gets the sequence and parameters right at each step.
*   **Prompt-Driven Approach:** Our agent invokes a single, high-level `Prompt` like `/quick-data:insight_generation_workshop_prompt`. The MCP server executes its own internal, pre-defined workflow, handling the entire chain of tool calls and returning a final, high-quality result.

### 4.3. Creating a Guided, Conversational Experience
`Prompts` enable the MCP server to become an active participant in the problem-solving dialogue.

As seen in the video, the response from a `Prompt` isn't just data; it's a conversation.
*   It provides a business insight: `Satisfied employees stay longer.`
*   It suggests a next step: `Want to visualize this with option 2?`

This guides the agent (and the user) towards a valuable outcome, making the entire system feel more intelligent and proactive.

## 5. Our System Implementation: Data Flow & Agent Responsibilities

We will implement a two-layer discovery model and assign clear responsibilities based on the MCP primitive tier list.

### Layer 1: Platform-Wide MCP Server Registry

Our platform will maintain a central service that acts as the "Yellow Pages" for all available MCP servers.

*   **Purpose:** To map high-level capabilities to server addresses.
*   **Example:**
    ```json
    {
      "data_analytics": "http://quick-data-mcp.internal:8080",
      "project_management": "http://jira-mcp.internal:8080",
      "code_repository": "http://github-mcp.internal:8080",
      "communications": "http://slack-mcp.internal:8080"
    }
    ```

### Layer 2: Agent Consumption of MCP Primitives

Different agents in our LangGraph architecture will interact with MCP primitives at different levels of abstraction.

| Agent Type | Primary MCP Primitive Consumed | Purpose & Workflow | Resulting Simplification |
| :--- | :--- | :--- | :--- |
| **`Chief Orchestrator`** | **Prompts** (High-Level) | **Strategic Planning.** Uses the `MCP Server Registry` to find relevant servers. It then invokes high-level discovery `Prompts` (like `list_mcp_assets_prompt`) to understand what workflows are available and delegates these high-level tasks to specialized agents via A2A. | Massively simplifies the orchestration logic. The orchestrator reasons about *what* needs to be done, not the low-level *how*. It plans with workflows, not atomic functions. |
| **Specialized Agents** (e.g., `DataAnalysisAgent`) | **Prompts** (Execution) | **Task Fulfillment.** Receives a high-level task from the Orchestrator (e.g., "run the `correlation_investigation_prompt`"). Its primary job is to connect to the correct MCP server and invoke the specified `Prompt`, returning the result. | These agents become simple, reliable "pass-throughs." Their logic is minimal, making them easy to build, test, and maintain. The complex workflow logic resides on the MCP server. |
| **`Executor`** (for simple, direct tasks) | **Tools** (Low-Level) | **Reliable Execution.** When a task is simple and maps to a single action (e.g., "load this dataset"), the Executor can call the `tools/list` method to get the exact `inputSchema` for validation before making a `tools/call`. | This ensures type safety and reduces runtime errors for simple, atomic operations, addressing the "semantic mismatch" risk for non-Prompt-based interactions. |

By adopting this model, our system becomes a hierarchy of intelligence. The `Chief Orchestrator` makes strategic decisions by consulting high-level `Prompts`. The specialized MCP servers encapsulate domain expertise within their own `Prompt`-driven workflows. This is a robust, scalable, and maintainable path to building a truly advanced agentic platform.

## Future Work (Thoughts)

