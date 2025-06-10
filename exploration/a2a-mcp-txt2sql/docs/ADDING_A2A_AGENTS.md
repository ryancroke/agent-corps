# Adding A2A Agents to A2A SQL Chat

This guide walks you through adding new A2A (Agent-to-Agent) agents to extend the intelligent workflow capabilities of the A2A SQL Chat application.

## Overview

A2A agents provide **complex business logic and multi-step reasoning** that coordinates multiple MCP servers. While MCP servers handle direct infrastructure access, A2A agents handle sophisticated workflows, validation, composition, and decision-making.

## A2A vs MCP: When to Use Each

| Use Case | Technology | Example |
|----------|------------|---------|
| **Direct Data Access** | MCP Server | Database queries, file system access, API calls |
| **Business Logic** | A2A Agent | SQL validation, email composition, data analysis |
| **Multi-step Workflows** | A2A Agent | "Analyze sales data and email report to stakeholders" |
| **Validation & Safety** | A2A Agent | Code review, content moderation, security checks |
| **Domain Expertise** | A2A Agent | Financial calculations, medical diagnosis, legal analysis |

## Current A2A Agents

The application currently includes:
- **SQL Validation Agent**: Validates SQL queries for safety and correctness using Python REPL MCP

## A2A Protocol Basics

Based on Google's A2A protocol, agents communicate via:

- **Agent Card**: Metadata describing agent capabilities (`/.well-known/agent.json`)
- **Tasks**: Work units with unique IDs and lifecycle states
- **Messages**: Communication turns between agents 
- **Skills**: Specific capabilities an agent can perform
- **Artifacts**: Structured outputs (data, files, results)

## Step-by-Step Integration Process

### Step 1: Create the A2A Agent

#### 1.1. Basic Agent Structure

Create a new agent file in `agents/your_agent_name.py`:

```python
"""
Your Agent Description - what it does and which MCP servers it uses.
"""

import asyncio
from typing import Any
from datetime import datetime

# Import MCP interfaces as needed
from mcp_servers.mcp_factory import create_mcp_interface


class YourAgentName:
    def __init__(self):
        self.agent_id = "your-agent-001"
        self.name = "Your Agent Name"
        self.version = "1.0.0"
        
        # MCP server connections (initialized in initialize())
        self.mcp_server1 = None
        self.mcp_server2 = None

    async def initialize(self):
        """Initialize MCP connections and dependencies."""
        # Connect to required MCP servers
        self.mcp_server1 = await create_mcp_interface("server1")
        self.mcp_server2 = await create_mcp_interface("server2")
        
        print(f"✓ {self.name} initialized")

    def get_agent_card(self) -> dict[str, Any]:
        """Return A2A Agent Card for discovery."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": "Detailed description of what this agent does",
            "version": self.version,
            "url": "http://localhost:8000/agents/your-agent",  # If exposing HTTP endpoint
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "multiTurn": True,  # If agent supports conversations
            },
            "skills": [
                {
                    "name": "your_primary_skill",
                    "description": "What this skill accomplishes",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "param1": {
                                "type": "string",
                                "description": "Description of parameter",
                            },
                            "param2": {
                                "type": "number", 
                                "description": "Optional numeric parameter",
                            }
                        },
                        "required": ["param1"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "string"},
                            "success": {"type": "boolean"},
                            "metadata": {"type": "object"},
                        },
                    },
                },
                # Add more skills as needed
            ],
        }

    async def your_primary_skill(self, param1: str, param2: float = 0.0) -> dict[str, Any]:
        """Implement your primary skill logic."""
        try:
            # Step 1: Use MCP server for data access
            data = await self.mcp_server1.query(f"Get data for {param1}")
            
            # Step 2: Process/analyze the data
            processed_result = self._process_data(data, param2)
            
            # Step 3: Use second MCP server if needed
            if processed_result["needs_external_call"]:
                external_result = await self.mcp_server2.query(
                    f"External operation: {processed_result['external_params']}"
                )
                processed_result["external_data"] = external_result
            
            # Step 4: Return structured result
            return {
                "result": processed_result["final_output"],
                "success": True,
                "metadata": {
                    "processing_time": processed_result["duration"],
                    "data_sources": ["mcp_server1", "mcp_server2"],
                    "timestamp": datetime.now().isoformat(),
                }
            }
            
        except Exception as e:
            return {
                "result": f"Skill failed: {str(e)}",
                "success": False,
                "metadata": {"error": str(e)}
            }

    def _process_data(self, data: str, param: float) -> dict[str, Any]:
        """Private method for data processing logic."""
        # Implement your business logic here
        return {
            "final_output": f"Processed: {data} with param {param}",
            "needs_external_call": param > 0.5,
            "external_params": f"param={param}",
            "duration": "0.1s"
        }

    async def process_a2a_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process A2A task message (standard interface)."""
        task = message.get("task", {})
        skill_name = task.get("skill")
        parameters = task.get("parameters", {})

        if skill_name == "your_primary_skill":
            result = await self.your_primary_skill(
                param1=parameters.get("param1"),
                param2=parameters.get("param2", 0.0)
            )
            return {"status": "completed", "artifacts": [result]}
        
        # Add more skill handlers as needed
        
        return {
            "status": "failed", 
            "error": f"Unknown skill: {skill_name}",
            "supported_skills": [skill["name"] for skill in self.get_agent_card()["skills"]]
        }

    async def close(self):
        """Clean up MCP connections."""
        if self.mcp_server1:
            await self.mcp_server1.close()
        if self.mcp_server2:
            await self.mcp_server2.close()


# Test function
async def test_agent():
    agent = YourAgentName()
    await agent.initialize()

    # Test the agent's primary skill
    result = await agent.your_primary_skill("test_input", 0.7)
    print(f"Skill result: {result}")
    
    # Test A2A message processing
    a2a_message = {
        "task": {
            "skill": "your_primary_skill",
            "parameters": {"param1": "test_via_a2a", "param2": 0.3}
        }
    }
    a2a_result = await agent.process_a2a_message(a2a_message)
    print(f"A2A result: {a2a_result}")

    await agent.close()


if __name__ == "__main__":
    asyncio.run(test_agent())
```

#### 1.2. Common Agent Patterns

**Data Analysis Agent:**
```python
class DataAnalysisAgent:
    """Analyzes data and generates insights using multiple data sources."""
    
    async def analyze_trend(self, dataset: str, timeframe: str) -> dict:
        # 1. Query database via SQLite MCP
        raw_data = await self.sqlite_mcp.query(f"SELECT * FROM {dataset} WHERE date >= '{timeframe}'")
        
        # 2. Process data (statistical analysis, trend detection)
        insights = self._calculate_trends(raw_data)
        
        # 3. Store results via ChromaDB MCP for future reference
        await self.chroma_mcp.query(f"Store analysis result: {insights}")
        
        return insights
```

**Email Composition Agent:**
```python
class EmailComposerAgent:
    """Composes and sends professional emails using templates and data."""
    
    async def compose_report_email(self, report_data: dict, recipients: list) -> dict:
        # 1. Get email template via filesystem MCP
        template = await self.filesystem_mcp.query("Read email template: report.html")
        
        # 2. Fill template with data
        email_content = self._fill_template(template, report_data)
        
        # 3. Send via email MCP server
        result = await self.email_mcp.query(f"Send email to {recipients}: {email_content}")
        
        return {"sent": True, "message_id": result}
```

**Multi-Agent Coordinator:**
```python
class WorkflowCoordinatorAgent:
    """Coordinates multiple agents for complex workflows."""
    
    async def sales_analysis_workflow(self, period: str) -> dict:
        # 1. Get data via data analysis agent
        analysis_result = await self._call_agent("data-analysis", "analyze_sales", {"period": period})
        
        # 2. Generate report via reporting agent  
        report_result = await self._call_agent("report-generator", "create_report", analysis_result)
        
        # 3. Send via email agent
        email_result = await self._call_agent("email-composer", "send_report", {
            "report": report_result, 
            "recipients": ["management@company.com"]
        })
        
        return {"workflow_complete": True, "steps": [analysis_result, report_result, email_result]}
```

### Step 2: LangGraph Integration

#### 2.1. Add to Orchestrator Initialization

Edit `enhanced_orchestrator.py`:

```python
class EnhancedSQLOrchestrator:
    def __init__(self):
        # Existing initialization...
        self.your_agent = YourAgentName()

    async def initialize(self):
        """Initialize all components."""
        # Existing MCP initialization...
        
        # Initialize A2A agents
        await self.validator.initialize()
        await self.your_agent.initialize()  # Add your agent
        
        # Rest of initialization...
```

#### 2.2. Integration Patterns

**Pattern 1: Direct Agent Call (Simple)**
For agents that provide standalone services:

```python
async def _call_your_agent(self, state: State) -> State:
    """Call your A2A agent directly."""
    try:
        # Create A2A message
        a2a_message = {
            "task": {
                "skill": "your_primary_skill",
                "parameters": {
                    "param1": state.get("user_query"),
                    "param2": state.get("some_numeric_param", 0.0)
                }
            }
        }
        
        # Call agent
        result = await self.your_agent.process_a2a_message(a2a_message)
        
        agents_used = state.get("agents_used", []) + ["your_agent"]
        
        if result["status"] == "completed":
            agent_output = result["artifacts"][0]
            return {
                **state,
                "agent_result": agent_output,
                "final_response": agent_output["result"],
                "agents_used": agents_used,
            }
        else:
            return {
                **state,
                "agent_result": {"error": result.get("error", "Unknown error")},
                "final_response": f"Agent failed: {result.get('error', 'Unknown error')}",
                "agents_used": agents_used,
            }
            
    except Exception as e:
        return {
            **state,
            "agent_result": {"error": str(e)},
            "final_response": f"Agent error: {str(e)}",
            "agents_used": state.get("agents_used", []) + ["your_agent_error"],
        }
```

**Pattern 2: Multi-Step Workflow (Complex)**
For agents that coordinate multiple operations:

```python
async def _workflow_with_agents(self, state: State) -> State:
    """Execute multi-step workflow using multiple agents."""
    workflow_steps = []
    
    try:
        # Step 1: Data analysis
        analysis_message = {
            "task": {
                "skill": "analyze_data",
                "parameters": {"query": state["user_query"]}
            }
        }
        analysis_result = await self.data_analysis_agent.process_a2a_message(analysis_message)
        workflow_steps.append(("analysis", analysis_result))
        
        # Step 2: Use analysis results for next step
        if analysis_result["status"] == "completed":
            composition_message = {
                "task": {
                    "skill": "compose_summary", 
                    "parameters": {"data": analysis_result["artifacts"][0]}
                }
            }
            composition_result = await self.composition_agent.process_a2a_message(composition_message)
            workflow_steps.append(("composition", composition_result))
        
        # Compile final response
        final_output = self._compile_workflow_results(workflow_steps)
        
        return {
            **state,
            "workflow_steps": workflow_steps,
            "final_response": final_output,
            "agents_used": state.get("agents_used", []) + ["data_analysis_agent", "composition_agent"],
        }
        
    except Exception as e:
        return {
            **state,
            "workflow_error": str(e),
            "final_response": f"Workflow failed: {str(e)}",
            "agents_used": state.get("agents_used", []) + ["workflow_error"],
        }
```

#### 2.3. Update Routing Logic

Add your agent to the routing system:

```python
async def _route_query(self, state: State) -> State:
    """Decide query type and routing."""
    query = state['user_query']
    
    routing_prompt = f"""
    Analyze this user query and determine the best routing:
    
    Query: {query}
    
    Choose ONE of these options:
    - SQL: Query needs database access (artists, albums, tracks, sales data)  
    - MEMORY: Query asks about previous conversations, history, or similar interactions
    - YOUR_AGENT: Query needs [describe your agent's capability]
    - DIRECT: General question that needs a direct LLM response
    
    Examples:
    - "How many artists are there?" → SQL
    - "What did we talk about earlier?" → MEMORY
    - "[Example query for your agent]" → YOUR_AGENT
    - "What is Python?" → DIRECT
    
    Respond with exactly one word: SQL, MEMORY, YOUR_AGENT, or DIRECT
    """
    
    response = await self.llm.ainvoke(routing_prompt)
    route_decision = response.content.strip().upper()
    
    # Set routing flags
    needs_sql = route_decision == "SQL"
    needs_memory = route_decision == "MEMORY"  
    needs_your_agent = route_decision == "YOUR_AGENT"
    query_type = route_decision.lower()
    
    return {
        **state,
        "needs_sql": needs_sql,
        "needs_memory": needs_memory,
        "needs_your_agent": needs_your_agent,
        "query_type": query_type,
    }

def _route_decision(self, state: State) -> str:
    """Route based on query type."""
    if state["needs_sql"]:
        return "generate_sql"
    elif state["needs_memory"]:
        return "search_memory" 
    elif state["needs_your_agent"]:
        return "call_your_agent"
    else:
        return "direct_response"
```

#### 2.4. Update Graph Building

Add nodes and edges for your agent:

```python
def _build_graph(self):
    """Build LangGraph with A2A validation."""
    graph = StateGraph(State)
    
    # Existing nodes...
    graph.add_node("call_your_agent", self._call_your_agent)
    
    # Update conditional edges to include your agent
    graph.add_conditional_edges("route", self._route_decision)
    
    # Add edge from your agent to END
    graph.add_edge("call_your_agent", END)
    
    return graph.compile(checkpointer=self.checkpointer)
```

### Step 3: Optional HTTP A2A Server

If you want to expose your agent as an HTTP A2A server (for external agents to call):

#### 3.1. Add Flask A2A Server

Create `agents/http_servers/your_agent_server.py`:

```python
"""
HTTP A2A Server for Your Agent.
Exposes the agent via standard A2A HTTP protocol.
"""

from flask import Flask, request, jsonify
import asyncio
import uuid
from agents.your_agent_name import YourAgentName

app = Flask(__name__)
agent = None

async def initialize_agent():
    global agent
    agent = YourAgentName()
    await agent.initialize()

# Agent Card endpoint (A2A discovery)
@app.get("/.well-known/agent.json")
def get_agent_card():
    """Serve agent card for A2A discovery."""
    return jsonify(agent.get_agent_card())

# A2A task endpoint
@app.post("/tasks/send") 
def handle_task():
    """Handle A2A task requests."""
    task_request = request.get_json()
    
    # Extract task information
    task_id = task_request.get("id")
    user_message = ""
    try:
        user_message = task_request["message"]["parts"][0]["text"]
    except Exception:
        return jsonify({"error": "Invalid request format"}), 400
    
    # Parse task from user message (simple approach)
    # In production, you'd want more sophisticated parsing
    if "analyze" in user_message.lower():
        skill = "your_primary_skill"
        params = {"param1": user_message, "param2": 1.0}
    else:
        skill = "your_primary_skill"
        params = {"param1": user_message}
    
    # Create A2A message
    a2a_message = {
        "task": {
            "skill": skill,
            "parameters": params
        }
    }
    
    # Process with agent
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(agent.process_a2a_message(a2a_message))
        
        if result["status"] == "completed":
            agent_output = result["artifacts"][0]
            agent_reply = agent_output["result"]
        else:
            agent_reply = f"Task failed: {result.get('error', 'Unknown error')}"
        
        # Format A2A response
        response_task = {
            "id": task_id,
            "status": {"state": "completed"},
            "messages": [
                task_request.get("message", {}),  # Original user message
                {
                    "role": "agent",
                    "parts": [{"text": agent_reply}]
                }
            ],
            "artifacts": result.get("artifacts", [])
        }
        
        return jsonify(response_task)
        
    except Exception as e:
        return jsonify({
            "id": task_id,
            "status": {"state": "failed"},
            "error": str(e)
        }), 500

if __name__ == "__main__":
    # Initialize agent
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_agent())
    
    # Start server
    app.run(host="0.0.0.0", port=5001, debug=True)
```

#### 3.2. Test External A2A Communication

Create `tests/test_a2a_external.py`:

```python
"""
Test external A2A agent communication.
"""

import requests
import uuid

def test_external_a2a_agent():
    """Test calling your agent via HTTP A2A protocol."""
    
    # 1. Discover agent
    agent_url = "http://localhost:5001"
    card_response = requests.get(f"{agent_url}/.well-known/agent.json")
    assert card_response.status_code == 200
    
    agent_card = card_response.json()
    print(f"Found agent: {agent_card['name']}")
    
    # 2. Send task
    task_id = str(uuid.uuid4())
    task_payload = {
        "id": task_id,
        "message": {
            "role": "user", 
            "parts": [{"text": "Analyze the sales data for Q4"}]
        }
    }
    
    task_response = requests.post(f"{agent_url}/tasks/send", json=task_payload)
    assert task_response.status_code == 200
    
    task_result = task_response.json()
    print(f"Task result: {task_result}")
    
    # 3. Verify response
    assert task_result["status"]["state"] == "completed"
    assert len(task_result["messages"]) == 2  # User + agent messages
    
    agent_message = task_result["messages"][-1]
    assert agent_message["role"] == "agent"
    print(f"Agent reply: {agent_message['parts'][0]['text']}")

if __name__ == "__main__":
    test_external_a2a_agent()
```

### Step 4: Testing Your A2A Agent

#### 4.1. Unit Tests

Create `tests/test_your_agent.py`:

```python
"""
Unit tests for YourAgentName.
"""

import asyncio
import pytest
from agents.your_agent_name import YourAgentName

@pytest.fixture
async def agent():
    """Create and initialize agent for testing."""
    agent = YourAgentName()
    await agent.initialize()
    yield agent
    await agent.close()

@pytest.mark.asyncio
async def test_agent_card(agent):
    """Test agent card structure."""
    card = agent.get_agent_card()
    
    assert card["id"] == "your-agent-001"
    assert card["name"] == "Your Agent Name"
    assert "skills" in card
    assert len(card["skills"]) > 0
    
    # Verify skill schema
    skill = card["skills"][0]
    assert "name" in skill
    assert "input_schema" in skill
    assert "output_schema" in skill

@pytest.mark.asyncio
async def test_primary_skill(agent):
    """Test the primary skill directly."""
    result = await agent.your_primary_skill("test_input", 0.5)
    
    assert "result" in result
    assert "success" in result
    assert "metadata" in result
    assert result["success"] is True

@pytest.mark.asyncio  
async def test_a2a_message_processing(agent):
    """Test A2A message processing."""
    message = {
        "task": {
            "skill": "your_primary_skill",
            "parameters": {"param1": "test_param", "param2": 0.8}
        }
    }
    
    result = await agent.process_a2a_message(message)
    
    assert result["status"] == "completed"
    assert "artifacts" in result
    assert len(result["artifacts"]) > 0
    
    artifact = result["artifacts"][0]
    assert artifact["success"] is True

@pytest.mark.asyncio
async def test_unknown_skill(agent):
    """Test handling of unknown skills."""
    message = {
        "task": {
            "skill": "nonexistent_skill",
            "parameters": {}
        }
    }
    
    result = await agent.process_a2a_message(message)
    
    assert result["status"] == "failed"
    assert "error" in result
```

#### 4.2. Integration Tests

Create `tests/test_agent_integration.py`:

```python
"""
Integration tests for agent within orchestrator.
"""

import asyncio
from enhanced_orchestrator import EnhancedSQLOrchestrator

async def test_agent_in_orchestrator():
    """Test agent integration within LangGraph orchestrator."""
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()
    
    try:
        # Test query that should route to your agent
        result = await orchestrator.run(
            "[Query that should trigger your agent]",
            "test-thread"
        )
        
        # Verify agent was used
        agents_used = result.get("agents_used", [])
        assert "your_agent" in agents_used
        
        # Verify response
        response = result.get("final_response", "")
        assert len(response) > 0
        assert "error" not in response.lower()
        
        print(f"Agent integration test passed: {response}")
        
    finally:
        await orchestrator.close()

if __name__ == "__main__":
    asyncio.run(test_agent_in_orchestrator())
```

### Step 5: Advanced Patterns

#### 5.1. Agent-to-Agent Communication

For agents that call other agents:

```python
class CoordinatorAgent:
    """Agent that coordinates other A2A agents."""
    
    def __init__(self):
        self.agent_registry = {}  # Map of agent_id -> agent_instance
    
    async def register_agent(self, agent_id: str, agent_instance):
        """Register another agent for coordination."""
        self.agent_registry[agent_id] = agent_instance
    
    async def call_agent(self, agent_id: str, skill: str, parameters: dict) -> dict:
        """Call another agent via A2A protocol."""
        if agent_id not in self.agent_registry:
            raise ValueError(f"Agent {agent_id} not registered")
        
        agent = self.agent_registry[agent_id]
        message = {
            "task": {
                "skill": skill,
                "parameters": parameters
            }
        }
        
        return await agent.process_a2a_message(message)
    
    async def orchestrate_workflow(self, workflow_spec: dict) -> dict:
        """Execute multi-agent workflow."""
        results = {}
        
        for step in workflow_spec["steps"]:
            agent_id = step["agent"]
            skill = step["skill"] 
            params = step.get("parameters", {})
            
            # Use results from previous steps
            if "depends_on" in step:
                for dep in step["depends_on"]:
                    params[dep] = results[dep]
            
            step_result = await self.call_agent(agent_id, skill, params)
            results[step["id"]] = step_result
        
        return results
```

#### 5.2. Streaming Responses

For agents that support streaming:

```python
class StreamingAnalysisAgent:
    """Agent that streams analysis results as they're computed."""
    
    async def stream_analysis(self, query: str):
        """Generator that yields partial results."""
        yield {"status": "starting", "progress": 0}
        
        # Step 1: Data retrieval
        yield {"status": "retrieving_data", "progress": 25}
        data = await self.get_data(query)
        
        # Step 2: Processing
        yield {"status": "processing", "progress": 50}
        insights = await self.analyze_data(data)
        
        # Step 3: Generating report
        yield {"status": "generating_report", "progress": 75}
        report = await self.generate_report(insights)
        
        # Final result
        yield {
            "status": "completed", 
            "progress": 100,
            "result": report
        }
```

## Best Practices

### 1. Agent Design Principles

- **Single Responsibility**: Each agent should have a clear, focused purpose
- **Stateless Execution**: Agents should not maintain state between calls
- **Error Resilience**: Always handle MCP server failures gracefully
- **Resource Cleanup**: Always close MCP connections in cleanup methods

### 2. A2A Message Standards

- **Consistent Schemas**: Use well-defined input/output schemas
- **Rich Metadata**: Include timing, versioning, and debugging info
- **Error Details**: Provide actionable error messages
- **Artifact Structure**: Use consistent artifact formats

### 3. Testing Strategies

- **Unit Tests**: Test agent skills in isolation
- **Integration Tests**: Test agent within orchestrator
- **A2A Protocol Tests**: Test external A2A communication
- **Performance Tests**: Test with realistic data volumes

### 4. Monitoring & Debugging

```python
import logging
from datetime import datetime

class MonitoredAgent:
    """Base class with monitoring capabilities."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.metrics = {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "avg_duration": 0.0
        }
    
    async def monitored_skill(self, *args, **kwargs):
        """Wrapper that adds monitoring to any skill."""
        start_time = datetime.now()
        self.metrics["calls"] += 1
        
        try:
            result = await self.actual_skill(*args, **kwargs)
            self.metrics["successes"] += 1
            self.logger.info(f"Skill completed successfully")
            return result
            
        except Exception as e:
            self.metrics["failures"] += 1
            self.logger.error(f"Skill failed: {e}")
            raise
            
        finally:
            duration = (datetime.now() - start_time).total_seconds()
            self.metrics["avg_duration"] = (
                self.metrics["avg_duration"] * (self.metrics["calls"] - 1) + duration
            ) / self.metrics["calls"]
```

## Common Use Cases

### Business Intelligence Agent
```python
# Analyzes business data and generates insights
skills: ["analyze_sales", "forecast_trends", "generate_kpi_report"]
mcp_servers: ["database", "analytics_engine", "reporting"]
```

### Content Moderation Agent  
```python
# Reviews content for policy compliance
skills: ["check_content_safety", "classify_sentiment", "flag_violations"]
mcp_servers: ["ml_models", "policy_db", "notification_system"]
```

### Customer Support Agent
```python
# Handles customer inquiries and escalations
skills: ["analyze_inquiry", "suggest_solutions", "escalate_to_human"]
mcp_servers: ["knowledge_base", "ticket_system", "customer_db"]
```

### DevOps Automation Agent
```python
# Automates deployment and monitoring tasks
skills: ["deploy_service", "monitor_health", "rollback_deployment"]
mcp_servers: ["kubernetes", "monitoring", "notification"]
```

## Troubleshooting

### Common Issues

1. **Agent Not Routing**: Check routing prompts and examples
2. **MCP Connection Failures**: Verify MCP server health and configuration
3. **A2A Schema Errors**: Validate input/output schemas match usage
4. **Performance Issues**: Add caching and async optimization

### Debug Commands

```bash
# Test agent directly
uv run agents/your_agent_name.py

# Test agent integration
uv run tests/test_agent_integration.py

# Test A2A HTTP server
uv run agents/http_servers/your_agent_server.py

# Monitor agent performance
uv run tools/agent_monitor.py --agent your_agent
```

## Next Steps

After adding an A2A agent:
- Consider exposing it as an HTTP A2A server for external access
- Add comprehensive monitoring and logging
- Create domain-specific workflows that coordinate multiple agents
- Implement caching for expensive operations
- Add authentication and rate limiting for production use

The combination of MCP servers (infrastructure) + A2A agents (intelligence) + LangGraph (orchestration) creates a powerful, extensible architecture for complex AI workflows.