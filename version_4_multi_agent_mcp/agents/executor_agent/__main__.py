# =============================================================================
# agents/executor_agent/__main__.py - Following your exact tell_time_agent pattern
# =============================================================================
# 🎯 Purpose:
# Start the ExecutorAgent server using Claude Sonnet 4 + Ansible AAP MCP tools
# Follows your exact tell_time_agent structure
# =============================================================================

from server.server import A2AServer
from models.agent import AgentCard, AgentCapabilities, AgentSkill
from agents.executor_agent.task_manager import AgentTaskManager
from agents.executor_agent.agent import ExecutorAgent
import click
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=10004, help="Port number for the server")
def main(host, port):
    """
    Start the ExecutorAgent server using Claude Sonnet 4
    Following your exact tell_time_agent pattern
    """
    # Define capabilities - same pattern as your tell_time_agent
    capabilities = AgentCapabilities(streaming=False)
    
    # Define the skill - using your exact pattern with required 'id' field
    skill = AgentSkill(
        id="deploy_monte_carlo",                                  # REQUIRED field
        name="Monte Carlo Deployment Execution",
        description="Executes Monte Carlo application deployment using Ansible AAP job templates",
        tags=["ansible", "deployment", "monte-carlo", "claude"],
        examples=[
            "Deploy Monte Carlo application",
            "Deploy Monte Carlo to monte-carlo-prod namespace",
            "Check status of job 123"
        ]
    )
    
    # Create agent card - using your exact AgentCard pattern
    agent_card = AgentCard(
        name="ExecutorAgent",
        description="Ansible AAP deployment executor for Monte Carlo applications using Claude Sonnet 4 + real MCP tools.",
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
        task_manager=AgentTaskManager(agent=ExecutorAgent())
    )
    
    print(f"🚀 ExecutorAgent (Claude Sonnet 4 + Ansible AAP MCP) starting on {host}:{port}")
    print(f"🔍 Agent Card: http://{host}:{port}/.well-known/agent.json")
    print(f"🧠 Powered by Claude Sonnet 4 + Real Ansible AAP MCP Tools")
    print(f"📋 Available MCP Tools: list_job_templates, run_job, job_status, job_logs")
    
    # Start listening for tasks
    server.start()


if __name__ == "__main__":
    main()
