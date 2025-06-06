# =============================================================================
# agents/servicenow_agent/__main__.py - ServiceNow Agent Entry Point
# =============================================================================
# 🎯 Purpose:
# Start the ServiceNow Agent server for ITSM operations
# Follows the exact same pattern as your other agents
# =============================================================================

from server.server import A2AServer
from models.agent import AgentCard, AgentCapabilities, AgentSkill
from agents.servicenow_agent.task_manager import ServiceNowTaskManager
from agents.servicenow_agent.agent import ServiceNowAgent
import click
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10005, help="Port number for the server")
def main(host, port):
    """
    Start the ServiceNow Agent server
    """
    # Define capabilities - same pattern as other agents
    capabilities = AgentCapabilities(streaming=False)

    # Define skills - ServiceNow specific
    skill = AgentSkill(
        id="servicenow_itsm",
        name="ServiceNow ITSM Operations",
        description="Manages ServiceNow incidents and ITSM workflows for deployment tracking",
        tags=["servicenow", "itsm", "incident", "tracking", "deployment", "claude"],
        examples=[
            "Create incident for Monte Carlo deployment to monte-carlo-staging",
            "Update incident INC0010001 with deployment progress",
            "Close incident INC0010002 with success status",
            "Search for Monte Carlo deployment incidents"
        ]
    )

    # Create agent card - same pattern as other agents
    agent_card = AgentCard(
        name="ServiceNowAgent",
        description="ServiceNow ITSM specialist using Claude Sonnet 4 for incident management and deployment tracking",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        capabilities=capabilities,
        skills=[skill]
    )

    # Create the ServiceNow agent
    servicenow_agent = ServiceNowAgent()

    # Start the A2A server - same pattern as other agents
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=ServiceNowTaskManager(agent=servicenow_agent)
    )

    print(f"🎫 ServiceNow Agent starting on {host}:{port}")
    print(f"🔍 Agent Card: http://{host}:{port}/.well-known/agent.json")
    print(f"🧠 Powered by Claude Sonnet 4")
    print(f"🛠️ ServiceNow MCP tools loaded")
    print(f"📋 Ready for ITSM operations!")

    # Start listening for tasks
    server.start()


if __name__ == "__main__":
    main()
