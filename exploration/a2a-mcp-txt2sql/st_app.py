"""
Polished Streamlit chat interface for A2A MCP SQL orchestrator.
Uses professional styling from your existing app.
"""

import asyncio
import uuid

import streamlit as st

from enhanced_orchestrator import EnhancedSQLOrchestrator, State


def get_custom_css():
    """Return the custom CSS for the application"""
    return """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap');

    * {
        font-family: 'Poppins', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
        color: #f1f5f9;
    }

    /* Main header */
    .main-header {
        text-align: center;
        padding: 3rem 2rem;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 25%, #ec4899 50%, #f59e0b 75%, #10b981 100%);
        color: white;
        border-radius: 24px;
        margin-bottom: 3rem;
        box-shadow: 0 20px 60px rgba(99, 102, 241, 0.4);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .main-header h1 {
        font-size: 3rem;
        font-weight: 800;
        margin-bottom: 1rem;
        text-shadow: 0 4px 8px rgba(0,0,0,0.3);
        background: linear-gradient(45deg, #fff, #e2e8f0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .main-header p {
        font-size: 1.3rem;
        font-weight: 400;
        opacity: 0.9;
        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    /* Chat container */
    .chat-container {
        background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
        padding: 3rem;
        border-radius: 24px;
        border: 1px solid rgba(99, 102, 241, 0.2);
        margin-bottom: 2rem;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        backdrop-filter: blur(20px);
        position: relative;
        overflow: hidden;
    }

    .chat-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899, #f59e0b);
        border-radius: 24px 24px 0 0;
    }

    /* Status indicators */
    .status-ready {
        background: linear-gradient(135deg, #10b981 0%, #34d399 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 16px;
        font-weight: 600;
        display: inline-block;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(16, 185, 129, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }

    /* Example queries */
    .example-queries {
        background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
        border-radius: 20px;
        padding: 2rem;
        margin: 1.5rem 0;
        border: 1px solid rgba(99, 102, 241, 0.3);
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }

    .example-title {
        font-weight: 700;
        color: #6366f1;
        margin-bottom: 1.5rem;
        font-size: 1.2rem;
    }

    .example-query {
        background: rgba(99, 102, 241, 0.1);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.8rem 0;
        cursor: pointer;
        transition: all 0.3s ease;
        border-left: 4px solid #6366f1;
        color: #f1f5f9;
        font-weight: 500;
    }

    .example-query:hover {
        transform: translateX(8px);
        background: rgba(99, 102, 241, 0.2);
        box-shadow: 0 5px 15px rgba(99, 102, 241, 0.3);
    }

    /* Chat messages */
    .stChatMessage {
        background: rgba(30, 41, 59, 0.6) !important;
        border-radius: 16px !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        backdrop-filter: blur(10px) !important;
        margin-bottom: 1rem !important;
    }

    /* Chat input */
    .stChatInput textarea {
        background: linear-gradient(145deg, #1e293b 0%, #334155 100%) !important;
        border: 2px solid rgba(99, 102, 241, 0.3) !important;
        border-radius: 16px !important;
        color: #f1f5f9 !important;
        font-family: 'Poppins', sans-serif !important;
    }

    .stChatInput textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
    }

    /* Spinner */
    .stSpinner > div {
        border-top-color: #6366f1 !important;
    }

    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {visibility: hidden;}

    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 12px;
    }

    ::-webkit-scrollbar-track {
        background: #1e293b;
        border-radius: 6px;
    }

    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        border-radius: 6px;
        border: 2px solid #1e293b;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
    }
</style>
"""


async def get_response(message: str, orchestrator: EnhancedSQLOrchestrator) -> str:
    """Get response from orchestrator."""
    return await orchestrator.run(message)


def main():
    # Page config
    st.set_page_config(
        page_title="🎵 SQL Chat AI",
        page_icon="🎵",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Apply custom CSS
    st.markdown(get_custom_css(), unsafe_allow_html=True)

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎵 SQL Chat AI</h1>
        <p>Chat with your Chinook Music Database using AI • Powered by A2A & MCP protocols</p>
    </div>
    """, unsafe_allow_html=True)

    if "orchestrator" not in st.session_state:
        with st.spinner("🚀 Initializing AI agents and MCP servers..."):
            st.session_state.orchestrator = EnhancedSQLOrchestrator()
            asyncio.run(st.session_state.orchestrator.initialize())
        st.markdown('<div class="status-ready">✅ System Ready - A2A Validation Active</div>', unsafe_allow_html=True)

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())

    # This list will now be our simple source of truth for the UI
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 2. Display the entire chat history from the simple session state list
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar=message.get("avatar")):
            st.markdown(message["content"])
            # Display bonus content like SQL if it exists
            if "sql_query" in message and message["sql_query"]:
                with st.expander("🔍 View Generated SQL"):
                    st.code(message["sql_query"], language="sql")

    # 3. Handle user input
    if prompt := st.chat_input("Ask me anything about the music database... 🎵"):
        # Append and display the user's message
        st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "🧑"})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)

        # Call the orchestrator and display the response
        with st.chat_message("assistant", avatar="🎵"):
            with st.spinner("🤖 AI agents collaborating..."):
                try:
                    orchestrator: EnhancedSQLOrchestrator = st.session_state.orchestrator

                    final_state: State = asyncio.run(orchestrator.run(
                        user_query=prompt,
                        thread_id=st.session_state.thread_id
                    ))

                    response_content = final_state.get("final_response", "Sorry, an error occurred.")
                    st.markdown(response_content)

                    # Also display the SQL in the same message bubble
                    sql_query_generated = final_state.get("sql_query")
                    if sql_query_generated:
                        with st.expander("🔍 View Generated SQL"):
                            st.code(sql_query_generated, language="sql")

                    # Append the full response data to our history list
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response_content,
                        "avatar": "🎵",
                        "sql_query": sql_query_generated
                    })

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"Error occurred: {str(e)}",
                        "avatar": "🎵"
                    })

# The example queries section can be added back if desired,
# checking `if not st.session_state.messages:`

if __name__ == "__main__":
    main()
