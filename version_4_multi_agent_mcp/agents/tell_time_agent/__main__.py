# =============================================================================
# agents/tell_time_agent/__main__.py - Fixed for proper models
# =============================================================================

from server.server import A2AServer
from models.agent import AgentCard, AgentCapabilities, AgentSkill
from agents.tell_time_agent.task_manager import AgentTaskManager
from agents.tell_time_agent.agent import TellTimeAgent

import click
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10002, help="Port number for the server")
def main(host, port):
    """
    Start the TellTimeAgent server using Claude Sonnet 4
    Fixed to match the actual model structure from models/agent.py
    """

    # Define capabilities - same as original
    capabilities = AgentCapabilities(streaming=False)

    # Define the skill - FIXED: add required 'id' field
    skill = AgentSkill(
        id="tell_time",                                           # REQUIRED field
        name="Tell Time Tool", 
        description="Replies with the current time using Claude Sonnet 4",
        tags=["time", "claude"],
        examples=["What time is it?", "Tell me the current time"]
    )

    # Create agent card - FIXED: use actual AgentCard fields from models/agent.py
    agent_card = AgentCard(
        name="TellTimeAgent",
        description="This agent replies with the current system time using Claude Sonnet 4.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        capabilities=capabilities,
        skills=[skill]
    )

    # Start the A2A server - same as original
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=AgentTaskManager(agent=TellTimeAgent())
    )
    
    print(f"🚀 TellTimeAgent (Claude Sonnet 4) starting on {host}:{port}")
    print(f"🕒 Agent Card: http://{host}:{port}/.well-known/agent.json")
    print(f"🧠 Powered by Claude Sonnet 4 instead of Gemini")

    # Start listening for tasks
    server.start()

if __name__ == "__main__":
    main()
