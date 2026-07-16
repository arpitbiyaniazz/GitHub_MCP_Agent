from ctypes import sizeof
import asyncio
import os
import streamlit as st
from textwrap import dedent
from uuid import uuid4
from agno.agent import Agent
from agno.models.mistral import MistralChat
from agno.run.agent import RunOutput
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters
from agno.db.redis import RedisDb
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

st.set_page_config(page_title="🐙 GitHub MCP Agent", page_icon="🐙", layout="wide")

st.markdown("<h1 class='main-header'>🐙 GitHub MCP Agent</h1>", unsafe_allow_html=True)
st.markdown("Explore GitHub repositories with natural language using the Model Context Protocol")

# Initialize Redis database for persistent chat memory
db = RedisDb(db_url="redis://localhost:6379")

def get_history_from_db(session_id: str):
    try:
        agent = Agent(
            model=MistralChat(id="mistral-large-latest"),
            db=db,
            add_history_to_context=True,
        )
        return agent.get_chat_history(session_id=session_id)
    except Exception:
        return []

# Initialize session state variables
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid4().hex

if "messages" not in st.session_state:
    st.session_state.messages = []
    # Load past messages from database
    history = get_history_from_db(st.session_state.session_id)
    for msg in history:
        if msg.role in ["user", "assistant"] and msg.content:
            st.session_state.messages.append({
                "role": msg.role,
                "content": msg.content
            })

with st.sidebar:
    st.header("🔑 Authentication")

    default_mistral = os.getenv("MISTRAL_API_KEY", "")
    Mistral_API_Key = st.text_input(
        "Mistral API Key", 
        value=default_mistral,
        type="password",
        help="Required for the AI agent to interpret queries and format results"
    )
    if Mistral_API_Key:
        os.environ["MISTRAL_API_KEY"] = Mistral_API_Key
    
    default_github = os.getenv("GITHUB_TOKEN", "")
    github_token = st.text_input(
        "GitHub Token", 
        value=default_github,
        type="password", 
        help="Create a token with repo scope at github.com/settings/tokens"
    )
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token

    st.markdown("---")
    st.header("🐙 Target Repository")
    repo = st.text_input("Repository", value="Shubhamsaboo/awesome-llm-apps", help="Format: owner/repo")

    st.markdown("---")
    st.header("💬 Chat Sessions")
    
    # Button to start a new chat
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.session_id = uuid4().hex
        st.session_state.messages = []
        st.rerun()

    # Load sessions from DB and allow switching
    try:
        sessions = db.get_sessions()
        session_ids = [s.session_id for s in sessions if s.session_id]
        
        # Ensure the current session_id is in the options list
        if st.session_state.session_id not in session_ids:
            session_ids.insert(0, st.session_state.session_id)
            
        selected_session = st.selectbox(
            "Select Session",
            options=session_ids,
            index=session_ids.index(st.session_state.session_id)
        )
        if selected_session != st.session_state.session_id:
            st.session_state.session_id = selected_session
            # Reset UI cache so we pull from the DB on reload
            if "messages" in st.session_state:
                del st.session_state.messages
            st.rerun()
    except Exception:
        # DB tables might not exist yet before the first run
        pass

    st.markdown("---")
    st.markdown("### Example Queries")
    
    st.markdown("**Issues**")
    st.markdown("- Show me issues labeled as bugs")
    st.markdown("- What issues are being actively discussed?")
    
    st.markdown("**Pull Requests**")
    st.markdown("- What PRs need review?")
    st.markdown("- Show me recent merged PRs")
    
    st.markdown("**Repository**")
    st.markdown("- Show repository health metrics")
    st.markdown("- Show repository activity patterns")

async def run_github_agent(message: str, session_id: str) -> str:
    if not os.getenv("GITHUB_TOKEN"):
        return "Error: GitHub token not provided"
    
    if not os.getenv("MISTRAL_API_KEY"):
        return "Error: Mistral API key not provided"
    
    try:
        server_params = StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "-e", "GITHUB_TOOLSETS",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                **os.environ,
                "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv('GITHUB_TOKEN'),
                "GITHUB_TOOLSETS": "repos,issues,pull_requests"
            }
        )

        async with MCPTools(server_params=server_params) as mcp_tools:
            agent = Agent(
                model=MistralChat(id="mistral-large-latest"),
                tools=[mcp_tools],
                db=db,
                add_history_to_context=True,
                num_history_runs=5,
                session_id=session_id,
                instructions=dedent("""\
                    You are a GitHub assistant. Help users explore repositories and their activity.
                    - Provide organized, concise insights about the repository
                    - Focus on facts and data from the GitHub API
                    - Use markdown formatting for better readability
                    - Present numerical data in tables when appropriate
                    - Include links to relevant GitHub pages when helpful
                    - Describe the context of issues, PRs, and repository activity clearly
                    - Answer the user's query based on the repository specified, and provide actionable insights
                    - Avoid speculation or unrelated information. If the query is unclear, ask for clarification.
                    - Provide the most relevant information about the repository, issues, and PRs based on the user's query.
                """),
                markdown=True,
            )
            
            response: RunOutput = await asyncio.wait_for(agent.arun(message), timeout=120.0)
            return response.content
                
    except asyncio.TimeoutError:
        return "Error: Request timed out after 120 seconds"
    except Exception as e:
        return f"Error: {str(e)}"

# Render chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Show setup/welcome info if conversation is empty
if len(st.session_state.messages) == 0:
    st.markdown(
        """<div class='info-box'>
        <h4>How to use this app:</h4>
        <ol>
            <li>Enter your <strong>Mistral API key</strong> in the sidebar (powers the AI agent)</li>
            <li>Enter your <strong>GitHub token</strong> in the sidebar</li>
            <li>Specify a target repository in the sidebar (e.g., Shubhamsaboo/awesome-llm-apps)</li>
            <li>Use the chat input below to ask questions about the repository</li>
        </ol>
        <p><strong>How it works:</strong></p>
        <ul>
            <li>Uses the official GitHub MCP server via Docker for real-time access to GitHub API</li>
            <li>AI Agent (powered by Mistral) interprets your queries and calls appropriate GitHub APIs</li>
            <li>Agno SQLite storage saves your conversation context, enabling follow-up questions</li>
        </ul>
        </div>""", 
        unsafe_allow_html=True
    )
    
    # Render quick prompt suggestions
    st.markdown("### Quick Templates")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🐛 Find bug issues", use_container_width=True):
            st.session_state.suggested_query = f"Find issues labeled as bugs in {repo}"
            st.rerun()
    with col2:
        if st.button("🔄 Show merged PRs", use_container_width=True):
            st.session_state.suggested_query = f"Show me recent merged PRs in {repo}"
            st.rerun()
    with col3:
        if st.button("📊 Analyze activity", use_container_width=True):
            st.session_state.suggested_query = f"Analyze repository activity trends in {repo}"
            st.rerun()

# Handle suggestion triggers
suggested_query = None
if "suggested_query" in st.session_state:
    suggested_query = st.session_state.suggested_query
    del st.session_state.suggested_query

# Input box for user prompt
prompt = st.chat_input("Ask me anything about the repository...")
if suggested_query:
    prompt = suggested_query

if prompt:
    # Verify authentication keys
    if not Mistral_API_Key and not os.getenv("MISTRAL_API_KEY"):
        st.error("Please enter your Mistral API key in the sidebar")
    elif not github_token and not os.getenv("GITHUB_TOKEN"):
        st.error("Please enter your GitHub token in the sidebar")
    else:
        # Display user input in UI
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing GitHub repository..."):
                # Append repository info to query if not present
                if repo and repo not in prompt:
                    full_query = f"{prompt} in {repo}"
                else:
                    full_query = prompt
                
                result = asyncio.run(run_github_agent(full_query, st.session_state.session_id))
                st.markdown(result)
        
        st.session_state.messages.append({"role": "assistant", "content": result})
        st.rerun()
