"""
FastAPI backend for A2A MCP SQL Chat application.
Replaces Streamlit to solve async/event loop issues.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data.chroma.create_db import create_chroma_db
from enhanced_orchestrator import EnhancedSQLOrchestrator, State


# Pydantic models for API
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sql_query: str | None = None
    timestamp: str


class QueryRequest(BaseModel):
    message: str
    thread_id: str | None = None


class QueryResponse(BaseModel):
    response: str
    sql_query: str | None = None
    thread_id: str
    timestamp: str
    mcp_servers_used: list[str] = []
    agents_used: list[str] = []


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]
    thread_id: str


# Global orchestrator instance
orchestrator: EnhancedSQLOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    global orchestrator
    print("🚀 Starting FastAPI server...")

    # Initialize ChromaDB first
    print("🔄 Initializing ChromaDB...")
    try:
        create_chroma_db()
        print("✅ ChromaDB initialized successfully!")
    except Exception as e:
        print(f"⚠️  ChromaDB initialization warning: {e}")
        print("   Continuing with startup...")

    print("🔄 Initializing Enhanced SQL Orchestrator...")
    orchestrator = EnhancedSQLOrchestrator()
    await orchestrator.initialize()
    print("✅ FastAPI server ready!")

    yield

    # Shutdown
    print("🔄 Shutting down...")
    if orchestrator:
        await orchestrator.close()
    print("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="🎵 SQL Chat AI",
    description="Chat with your Chinook Music Database using AI • Powered by A2A & MCP protocols",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory chat history (in production, use a database)
chat_sessions: dict[str, list[ChatMessage]] = {}


@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """Serve the main chat interface."""
    return FileResponse("static/index.html")


@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process a user query through the orchestrator."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    # Generate thread ID if not provided
    thread_id = request.thread_id or str(uuid.uuid4())

    try:
        # Process query through orchestrator
        final_state: State = await orchestrator.run(
            user_query=request.message, thread_id=thread_id
        )

        response_content = final_state.get(
            "final_response", "Sorry, an error occurred."
        )
        sql_query = final_state.get("sql_query")
        timestamp = datetime.now().isoformat()

        # Store in chat history
        if thread_id not in chat_sessions:
            chat_sessions[thread_id] = []

        # Add user message
        chat_sessions[thread_id].append(
            ChatMessage(role="user", content=request.message, timestamp=timestamp)
        )

        # Add assistant response
        chat_sessions[thread_id].append(
            ChatMessage(
                role="assistant",
                content=response_content,
                sql_query=sql_query,
                timestamp=timestamp,
            )
        )

        return QueryResponse(
            response=response_content,
            sql_query=sql_query,
            thread_id=thread_id,
            timestamp=timestamp,
            mcp_servers_used=final_state.get("mcp_servers_used", []),
            agents_used=final_state.get("agents_used", []),
        )

    except Exception as e:
        print(f"❌ Query processing failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Query processing failed: {str(e)}"
        ) from e


@app.get("/api/history/{thread_id}", response_model=ChatHistoryResponse)
async def get_chat_history(thread_id: str):
    """Get chat history for a thread."""
    messages = chat_sessions.get(thread_id, [])
    return ChatHistoryResponse(messages=messages, thread_id=thread_id)


@app.delete("/api/history/{thread_id}")
async def clear_chat_history(thread_id: str):
    """Clear chat history for a thread."""
    if thread_id in chat_sessions:
        del chat_sessions[thread_id]
    return {"message": "Chat history cleared"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not ready")

    # Check MCP server health
    mcp_healthy = await orchestrator.sqlite_mcp.health_check()

    return {
        "status": "healthy" if mcp_healthy else "degraded",
        "orchestrator": "ready",
        "mcp_server": "healthy" if mcp_healthy else "unhealthy",
        "timestamp": datetime.now().isoformat(),
    }


# WebSocket endpoint for real-time chat (optional enhancement)
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """WebSocket endpoint for real-time chat."""
    await manager.connect(websocket)
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            if not orchestrator:
                await websocket.send_text("Error: Orchestrator not ready")
                continue

            try:
                # Process query
                final_state: State = await orchestrator.run(
                    user_query=data, thread_id=thread_id
                )

                response_content = final_state.get(
                    "final_response", "Sorry, an error occurred."
                )
                sql_query = final_state.get("sql_query")

                # Send response back
                response = {
                    "response": response_content,
                    "sql_query": sql_query,
                    "timestamp": datetime.now().isoformat(),
                }

                await websocket.send_json(response)

            except Exception as e:
                await websocket.send_text(f"Error: {str(e)}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    print("🎵 Starting SQL Chat AI FastAPI Server")
    print("📍 Open: http://localhost:8000")

    uvicorn.run(
        "fastapi_app:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
