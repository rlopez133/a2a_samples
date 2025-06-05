# =============================================================================
# agents/host_agent/entry.py - Updated for Claude-based Host Agent
# =============================================================================
# 🎯 Purpose:
# Start the Claude-based Host Agent (orchestrator) server
# Replaces the Gemini imports with Claude orchestrator
# =============================================================================

from server.server import A2AServer
from models.agent import AgentCard, AgentCapabilities, AgentSkill
from agents.host_agent.orchestrator import ClaudeOrchestratorAgent, ClaudeOrchestratorTaskManager
from utilities.a2a.agent_discovery import DiscoveryClient
import click
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10000, help="Port number for the server")
def main(host, port):
    """
    Start the Claude-based Host Agent (orchestrator) server
    """
    
    async def discover_agents():
        """Discover available A2A agents"""
        discovery = DiscoveryClient()
        agent_cards = await discovery.list_agent_cards()
        logger.info(f"Discovered {len(agent_cards)} agents: {[card.name for card in agent_cards]}")
        return agent_cards
    
    # Discover available agents
    agent_cards = asyncio.run(discover_agents())
    
    # Define capabilities
    capabilities = AgentCapabilities(streaming=False)
    
    # Define skills
    skill = AgentSkill(
        id="orchestrate_agents",
        name="Agent Orchestration",
        description="Coordinates between specialized agents and MCP tools for complex workflows",
        tags=["orchestration", "coordination", "claude", "monte-carlo", "deployment"],
        examples=[
            "Deploy Monte Carlo to monte-carlo-risk-sim",
            "Assess cluster readiness for monte-carlo-prod",
            "What time is it?",
            "Greet me"
        ]
    )
    
    # Create agent card
    agent_card = AgentCard(
        name="ClaudeHostAgent",
        description="Claude Sonnet 4 orchestrator that coordinates between A2A agents and MCP tools",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        capabilities=capabilities,
        skills=[skill]
    )
    
    # Create orchestrator with discovered agents
    orchestrator = ClaudeOrchestratorAgent(agent_cards)
    
    # Start the A2A server
    server = A2AServer(
        host=host,
        port=port,
        agent_card=agent_card,
        task_manager=ClaudeOrchestratorTaskManager(agent=orchestrator)
    )
    
    print(f"🚀 Claude Host Agent (Orchestrator) starting on {host}:{port}")
    print(f"🔍 Agent Card: http://{host}:{port}/.well-known/agent.json")
    print(f"🧠 Powered by Claude Sonnet 4")
    print(f"🤖 Coordinating agents: {[card.name for card in agent_cards]}")
    print(f"🛠️ Available MCP tools: {len(orchestrator.mcp_tools)} tools loaded")
    print(f"📋 Ready for Monte Carlo deployment workflows!")
    
    # Start listening for tasks
    server.start()


if __name__ == "__main__":
    main()
