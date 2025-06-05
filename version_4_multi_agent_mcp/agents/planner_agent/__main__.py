# =============================================================================
# agents/planner_agent/__main__.py - Following your exact tell_time_agent pattern
# =============================================================================
# 🎯 Purpose:
# Start the PlannerAgent server using Claude Sonnet 4 + Kubernetes MCP tools
# Follows your exact tell_time_agent structure
# =============================================================================

from server.server import A2AServer
from models.agent import AgentCard, AgentCapabilities, AgentSkill
from agents.planner_agent.task_manager import AgentTaskManager
from agents.planner_agent.agent import PlannerAgent
import click
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10003, help="Port number for the server")
def main(host, port):
    """
    Start the PlannerAgent server using Claude Sonnet 4
    Following your exact tell_time_agent pattern
    """
    # Define capabilities - same pattern as your tell_time_agent
    capabilities = AgentCapabilities(streaming=False)
    
    # Define the skill - using your exact pattern with required 'id' field
    skill = AgentSkill(
        id="assess_cluster_readiness",                            # REQUIRED field
        name="Monte Carlo Cluster Planning",
        description="Assesses Kubernetes cluster readiness for Monte Carlo deployment using real MCP tools",
        tags=["kubernetes", "planning", "monte-carlo", "claude"],
        examples=[
            "Assess cluster readiness for Monte Carlo deployment",
            "Check if the cluster is ready for monte-carlo-risk-sim",
            "What's the current state of the Kubernetes cluster?"
        ]
    )
    
    # Create agent card - using your exact AgentCard pattern
    agent_card = AgentCard(
        name="PlannerAgent",
        description="Kubernetes cluster planning agent for Monte Carlo deployment using Claude Sonnet 4 + real MCP tools.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        capabilities=capabilities,
        skills=[skill]
    )
    
    # Start the A2A server - same as your tell_time_agent
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=AgentTaskManager(agent=PlannerAgent())
    )
    
    print(f"🎯 PlannerAgent (Claude Sonnet 4 + Kubernetes MCP) starting on {host}:{port}")
    print(f"🔍 Agent Card: http://{host}:{port}/.well-known/agent.json")
    print(f"🧠 Powered by Claude Sonnet 4 + Real Kubernetes MCP Tools")
    print(f"📋 Available MCP Tools: configuration_get, namespaces_list, pods_list, pods_list_in_namespace")
    
    # Start listening for tasks
    server.start()


if __name__ == "__main__":
    main()
