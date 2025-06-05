# =============================================================================
# agents/host_agent/claude_orchestrator.py
# =============================================================================
# 🎯 Purpose:
# Claude-based orchestrator that coordinates between A2A agents and MCP tools
# Same functionality as the Gemini orchestrator but using Claude Sonnet 4
# =============================================================================

import uuid
import logging
import asyncio
import os
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# A2A infrastructure imports
from server.task_manager import InMemoryTaskManager
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, TaskStatus, TaskState, TextPart

# A2A discovery & connector imports
from utilities.a2a.agent_discovery import DiscoveryClient
from utilities.a2a.agent_connect import AgentConnector

# MCP connector import
from utilities.mcp.mcp_connect import MCPConnector

# Import AgentCard model for typing
from models.agent import AgentCard

# Logging setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ClaudeOrchestratorAgent:
    """
    🤖 Claude-based OrchestratorAgent:
      - Discovers A2A agents via DiscoveryClient → list of AgentCards
      - Connects to each A2A agent with AgentConnector
      - Discovers MCP servers via MCPConnector and loads MCP tools
      - Uses Claude Sonnet 4 to decide which tools to call
      - Routes user queries by picking and invoking the correct tool
    """
    
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        """
        Initialize the Claude-based orchestrator with discovered A2A agents and MCP tools.
        """
        # Initialize Claude client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
            
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Build connectors for each A2A agent
        self.connectors = {}
        for card in agent_cards:
            self.connectors[card.name] = AgentConnector(card.name, card.url)
            logger.info(f"Registered A2A connector for: {card.name}")

        # Load all MCP tools once at startup
        self.mcp = MCPConnector()
        self.mcp_tools = self.mcp.get_tools()
        logger.info(f"Loaded {len(self.mcp_tools)} MCP tools")

        self._user_id = "orchestrator_user"

    def _get_available_agents(self) -> list[str]:
        """Return list of available agent names."""
        return list(self.connectors.keys())

    def _get_available_mcp_tools(self) -> list[str]:
        """Return list of available MCP tool names."""
        return [tool.name for tool in self.mcp_tools]

    async def _delegate_task(self, agent_name: str, message: str, session_id: str) -> str:
        """
        Forward a message to a child agent and return its reply.
        """
        if agent_name not in self.connectors:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        try:
            # Send the task and await its completion
            task = await self.connectors[agent_name].send_task(message, session_id)
            
            # Extract the last history entry if present
            if task.history and len(task.history) > 1:
                return task.history[-1].parts[0].text
            return "No response from agent"
            
        except Exception as e:
            logger.error(f"Error delegating to {agent_name}: {e}")
            return f"Error communicating with {agent_name}: {str(e)}"

    async def _call_mcp_tool(self, tool_name: str, args: dict) -> str:
        """
        Call an MCP tool and return its result.
        """
        try:
            # Find the tool
            tool = next((t for t in self.mcp_tools if t.name == tool_name), None)
            if not tool:
                return f"MCP tool {tool_name} not found"
            
            # Call the tool
            result = await tool.run(args)
            return str(result)
            
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}")
            return f"Error calling {tool_name}: {str(e)}"

    def _build_system_prompt(self, session_id: str) -> str:
        """
        Build the system prompt for Claude with available tools and capabilities.
        """
        available_agents = self._get_available_agents()
        available_mcp_tools = self._get_available_mcp_tools()
        
        return f"""You are an orchestrator agent that coordinates between specialized agents and MCP tools.

AVAILABLE A2A AGENTS:
{', '.join(available_agents)}

AVAILABLE MCP TOOLS:
{', '.join(available_mcp_tools)}

COORDINATION CAPABILITIES:
1. For deployment requests involving Monte Carlo applications:
   - First delegate to PlannerAgent to assess cluster readiness
   - Then delegate to ExecutorAgent to perform the deployment
   
2. For assessment requests:
   - Delegate to PlannerAgent for cluster assessment
   
3. For direct tool needs:
   - Use MCP tools directly for specific operations

AGENT SPECIALIZATIONS:
- PlannerAgent: Kubernetes cluster assessment, namespace checking
- ExecutorAgent: Ansible AAP deployment execution, job monitoring
- TellTimeAgent: Current time information
- GreetingAgent: Personalized greetings

WORKFLOW EXAMPLES:
User: "Deploy Monte Carlo to namespace-xyz"
→ 1. Call PlannerAgent: "Assess cluster readiness for namespace-xyz"
→ 2. If ready, call ExecutorAgent: "Deploy Monte Carlo to namespace-xyz" 
→ 3. Return coordinated results

User: "Check cluster status for monte-carlo-prod"
→ Call PlannerAgent: "Assess monte-carlo-prod namespace"

Session ID: {session_id}

Analyze the user request and determine the best approach. If it involves Monte Carlo deployment, coordinate between PlannerAgent and ExecutorAgent. Be specific about which agent to call and what message to send."""

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Primary entrypoint: handles a user query using Claude to orchestrate tools.
        """
        try:
            # Build system prompt with current context
            system_prompt = self._build_system_prompt(session_id)
            
            # Call Claude to analyze the request and determine actions
            analysis_response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": f"Analyze this request and determine what actions to take: {query}"
                }]
            )
            
            analysis = analysis_response.content[0].text if analysis_response.content else ""
            logger.info(f"Claude analysis: {analysis}")
            
            # Execute the plan based on Claude's analysis
            result = await self._execute_plan(query, analysis, session_id)
            
            return result
            
        except Exception as e:
            logger.error(f"ClaudeOrchestratorAgent error: {e}")
            return f"Orchestration error: {str(e)}"

    async def _execute_plan(self, original_query: str, analysis: str, session_id: str) -> str:
        """
        Execute the orchestration plan based on Claude's analysis.
        """
        try:
            # For deployment requests, coordinate PlannerAgent → ExecutorAgent
            if any(keyword in original_query.lower() for keyword in ['deploy', 'deployment']):
                return await self._handle_deployment_workflow(original_query, session_id)
            
            # For assessment requests, just use PlannerAgent
            elif any(keyword in original_query.lower() for keyword in ['assess', 'check', 'status', 'ready']):
                return await self._delegate_task("PlannerAgent", original_query, session_id)
            
            # For time requests, use TellTimeAgent
            elif any(keyword in original_query.lower() for keyword in ['time', 'date']):
                return await self._delegate_task("TellTimeAgent", original_query, session_id)
            
            # For greetings, use GreetingAgent
            elif any(keyword in original_query.lower() for keyword in ['greet', 'hello', 'hi']):
                return await self._delegate_task("GreetingAgent", original_query, session_id)
            
            # Otherwise, let Claude decide based on analysis
            else:
                return await self._handle_general_query(original_query, analysis, session_id)
                
        except Exception as e:
            logger.error(f"Error executing plan: {e}")
            return f"Error executing orchestration plan: {str(e)}"

    async def _handle_deployment_workflow(self, query: str, session_id: str) -> str:
        """
        Handle Monte Carlo deployment workflow: PlannerAgent → ExecutorAgent
        """
        try:
            # Step 1: Get cluster assessment from PlannerAgent
            logger.info("Step 1: Getting cluster assessment from PlannerAgent")
            assessment = await self._delegate_task("PlannerAgent", query, session_id)
            
            # Step 2: If assessment is positive, proceed with ExecutorAgent
            if any(keyword in assessment.lower() for keyword in ['ready', 'healthy', 'accessible']):
                logger.info("Step 2: Cluster ready, proceeding with deployment via ExecutorAgent")
                deployment = await self._delegate_task("ExecutorAgent", query, session_id)
                
                return f"**Monte Carlo Deployment Workflow Complete**\n\n**Assessment Results:**\n{assessment}\n\n**Deployment Results:**\n{deployment}"
            else:
                return f"**Monte Carlo Deployment Workflow - Assessment Failed**\n\n**Assessment Results:**\n{assessment}\n\n**Recommendation:** Resolve assessment issues before proceeding with deployment."
            
        except Exception as e:
            logger.error(f"Error in deployment workflow: {e}")
            return f"Error in deployment workflow: {str(e)}"

    async def _handle_general_query(self, query: str, analysis: str, session_id: str) -> str:
        """
        Handle general queries based on Claude's analysis.
        """
        # This could be enhanced to parse Claude's analysis and extract specific tool calls
        # For now, provide a helpful response
        available_agents = self._get_available_agents()
        return f"I can help coordinate between these agents: {', '.join(available_agents)}. Please specify what you'd like me to help with:\n\n- Monte Carlo deployment: 'Deploy Monte Carlo to [namespace]'\n- Cluster assessment: 'Assess cluster for [namespace]'\n- Current time: 'What time is it?'\n- Greetings: 'Greet me'\n\nYour query: {query}"


class ClaudeOrchestratorTaskManager(InMemoryTaskManager):
    """
    TaskManager wrapper: exposes ClaudeOrchestratorAgent.invoke()
    over the `tasks/send` JSON-RPC endpoint.
    """
    def __init__(self, agent: ClaudeOrchestratorAgent):
        super().__init__()
        self.agent = agent

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """Extract raw user text from JSON-RPC request."""
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Handle `tasks/send` calls:
          1) Store incoming message in memory
          2) Invoke the orchestrator to get a reply
          3) Append the reply, mark task COMPLETED
          4) Return the full Task in the response
        """
        logger.info(f"ClaudeOrchestratorTaskManager received task {request.params.id}")
        
        # Store or update the task record
        task = await self.upsert_task(request.params)
        
        # Extract the text and invoke orchestration logic
        user_text = self._get_user_text(request)
        reply_text = await self.agent.invoke(user_text, request.params.sessionId)
        
        # Wrap reply in a Message object
        msg = Message(role="agent", parts=[TextPart(text=reply_text)])
        
        # Safely append reply and update status under lock
        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(msg)
        
        # Return the RPC response including the updated task
        return SendTaskResponse(id=request.id, result=task)
