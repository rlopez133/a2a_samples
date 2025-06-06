# =============================================================================
# agents/host_agent/orchestrator.py - PRACTICAL HYBRID VERSION (FIXED)
# =============================================================================
# 🎯 Purpose:
# Best of both worlds: Dynamic workflow generation + reliable execution
# - Single Claude call for workflow generation
# - Smart hardcoded logic for progressive ServiceNow updates
# - No timeouts, but rich ServiceNow audit trail
# - FIXED: Proper incident closure with correct incident number
# =============================================================================

import uuid
import logging
import asyncio
import os
import re
import anthropic
import json
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
    🤖 Practical Hybrid Claude-based OrchestratorAgent:
      - Dynamic workflow generation (single Claude call)
      - Smart execution with progressive ServiceNow updates
      - Reliable and fast execution without timeouts
      - FIXED: Proper incident closure logic
    """

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        """
        Initialize the practical hybrid orchestrator.
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

    def _should_use_dynamic_workflow(self, query: str) -> bool:
        """
        Determine if query needs multi-agent orchestration.
        
        PRINCIPLE: Only use complex workflow when you actually need 
        coordination across ServiceNow + Kubernetes + Ansible with state tracking.
        Everything else should be handled simply.
        """
        query_lower = query.lower()
        
        # Complex workflow ONLY for explicit orchestration requests
        orchestration_indicators = [
            # Multi-step enterprise processes
            "deploy", "deployment", "provision", "rollback", "migrate",
            # Cross-system coordination phrases  
            "create incident for", "track deployment", "deploy and track",
            "coordinate", "orchestrate", "workflow", "process",
            # Multi-agent operations
            "assess and deploy", "deploy then verify", "provision with monitoring"
        ]
        
        # Only escalate to complex if it clearly needs orchestration
        needs_orchestration = any(indicator in query_lower for indicator in orchestration_indicators)
        
        # Default to simple for everything else
        return needs_orchestration

    def _extract_namespace(self, query: str) -> str:
        """Extract namespace from deployment query"""
        if not query:
            return 'unknown'

        words = query.lower().split()

        # Look for explicit namespace patterns
        for i, word in enumerate(words):
            if word in ['to', 'namespace', 'into'] and i + 1 < len(words):
                namespace = words[i + 1].strip('.,!?')
                logger.info(f"Found namespace via keyword: {namespace}")
                return namespace
            if 'monte-carlo' in word or 'monte_carlo' in word:
                namespace = word.strip('.,!?')
                logger.info(f"Found Monte Carlo namespace: {namespace}")
                return namespace

        # Try regex patterns for common deployment syntax
        patterns = [
            r'deploy(?:ment)?\s+(?:to\s+)?(\S+)',
            r'namespace[:\s]+(\S+)',
            r'target[:\s]+(\S+)',
            r'(?:to|into)\s+(\S+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, query.lower())
            if match:
                namespace = match.group(1).strip('.,!?')
                logger.info(f"Found namespace via regex: {namespace}")
                return namespace

        logger.warning(f"Could not extract namespace from query: {query}")
        return 'unknown'

    def _extract_system_info(self, response: str) -> dict:
        """
        Extract system information from agent responses
        """
        info = {}

        if not response:
            return info

        response_upper = response.upper()

        # ServiceNow incident numbers - always INC followed by digits
        incident_match = re.search(r'\b(INC\d+)\b', response_upper)
        if incident_match:
            info['incident_number'] = incident_match.group(1)

        # Ansible job IDs - look for various patterns
        job_patterns = [
            r'Job ID[:\s]*`?(\d+)`?',
            r'job[:\s]*(\d+)',
            r'ID[:\s]*(\d+)',
            r'tracking[:\s]*ID[:\s]*`?(\d+)`?'
        ]

        for pattern in job_patterns:
            job_match = re.search(pattern, response, re.IGNORECASE)
            if job_match:
                info['job_id'] = job_match.group(1)
                break

        return info

    def _assess_readiness(self, response: str) -> bool:
        """Check if assessment indicates readiness"""
        if not response:
            return False

        positive_indicators = ['ready', 'healthy', 'accessible', 'available', 'running', 'active', 'ready_for_ansible_deployment', 'proceed', 'cleared']
        negative_indicators = ['failed', 'error', 'unavailable', 'down', 'unhealthy', 'not ready', 'cannot proceed']

        response_lower = response.lower()

        # Check for negative indicators first
        if any(indicator in response_lower for indicator in negative_indicators):
            return False

        # Check for positive indicators
        return any(indicator in response_lower for indicator in positive_indicators)

    async def _execute_practical_hybrid_workflow(self, query: str, session_id: str) -> str:
        """
        Execute practical hybrid workflow with single Claude call + smart execution
        """
        try:
            available_agents = self._get_available_agents()
            namespace = self._extract_namespace(query)

            # Single Claude call to generate workflow structure
            workflow_prompt = f"""Generate a deployment workflow for: {query}

Available agents: {', '.join(available_agents)}
Target namespace: {namespace}

Agent capabilities:
- ServiceNowAgent: Create/update/close incidents
- PlannerAgent: Kubernetes assessment, returns readiness status
- ExecutorAgent: Ansible deployment, returns job IDs

Create a logical workflow as JSON array. Focus on the main steps:

Example:
[
  {{"agent": "ServiceNowAgent", "task": "Create incident for Monte Carlo deployment to {namespace} namespace"}},
  {{"agent": "PlannerAgent", "task": "Assess cluster readiness for {namespace} namespace"}},
  {{"agent": "ExecutorAgent", "task": "Deploy Monte Carlo application to {namespace} namespace"}},
  {{"agent": "ServiceNowAgent", "task": "Close incident with deployment results"}}
]

Return ONLY the JSON array:"""

            logger.info("Generating practical hybrid workflow...")

            workflow_response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": workflow_prompt}]
            )

            workflow_text = workflow_response.content[0].text.strip()

            # Extract JSON from response
            json_match = re.search(r'\[.*\]', workflow_text, re.DOTALL)
            if not json_match:
                return f"Error: Could not parse workflow plan"

            workflow_steps = json.loads(json_match.group(0))

            if not workflow_steps:
                return "Error: No workflow steps generated"

            logger.info(f"Generated practical hybrid workflow with {len(workflow_steps)} steps")

            # Execute the workflow with smart ServiceNow progression
            return await self._execute_workflow_with_progression(query, workflow_steps, namespace, session_id)

        except Exception as e:
            logger.error(f"Error in practical hybrid workflow: {e}")
            return f"Error executing practical hybrid workflow: {str(e)}"

    async def _execute_workflow_with_progression(self, original_query: str, workflow: list, namespace: str, session_id: str) -> str:
        """
        Execute workflow with smart progressive ServiceNow updates
        FIXED: Proper incident closure with correct incident number
        """
        try:
            results = []
            context = {
                "namespace": namespace,
                "deployment_ready": False,
                "deployment_success": False,
                "incident_number": None,
                "job_id": None
            }

            for i, step in enumerate(workflow, 1):
                agent_name = step.get("agent", "")
                task_description = step.get("task", "")

                logger.info(f"Step {i}: Calling {agent_name} with task: {task_description}")

                # Handle final ServiceNow closure FIRST - before any execution
                if agent_name == "ServiceNowAgent" and any(keyword in task_description.lower() for keyword in ['close', 'final', 'completion', 'update incident']):
                    # This is the final ServiceNow step - make it specific and SKIP the original call
                    if context.get("incident_number"):
                        if context.get("deployment_success"):
                            job_info = f" Job ID {context.get('job_id')} completed successfully." if context.get("job_id") else ""
                            enhanced_task = f"Update incident {context['incident_number']} with work_notes 'Monte Carlo deployment to {namespace} namespace completed successfully.{job_info} Application is ready for use.' and state 6"
                        else:
                            enhanced_task = f"Update incident {context['incident_number']} with work_notes 'Monte Carlo deployment to {namespace} namespace failed. Investigation required.' and state 2"

                        # Execute ONLY the enhanced task
                        enhanced_result = await self._delegate_task("ServiceNowAgent", enhanced_task, session_id)
                        results.append(f"**Step {i} - {agent_name}**: ✅ Updated incident **{context['incident_number']}**\n\nUpdates applied: {enhanced_result}")
                        continue  # Skip all other processing for this step

                # Execute the step normally for non-final ServiceNow steps
                if agent_name in self.connectors:
                    result = await self._delegate_task(agent_name, task_description, session_id)
                    results.append(f"**Step {i} - {agent_name}**: ✅ {result}")

                    # Extract system information
                    system_info = self._extract_system_info(result)
                    context.update(system_info)

                    # Smart progressive ServiceNow updates
                    if agent_name == "ServiceNowAgent" and "create" in task_description.lower():
                        # Incident created - extract incident number
                        logger.info(f"ServiceNow incident created: {context.get('incident_number', 'Unknown')}")

                    elif agent_name == "PlannerAgent":
                        # Assessment completed - add progress update
                        context["deployment_ready"] = self._assess_readiness(result)
                        if context.get("incident_number"):
                            if context["deployment_ready"]:
                                update_task = f"Update incident {context['incident_number']} with work_notes 'Cluster assessment completed - {namespace} namespace is healthy and ready for deployment. Proceeding with deployment execution.'"
                            else:
                                update_task = f"Update incident {context['incident_number']} with work_notes 'Cluster assessment completed - {namespace} namespace is not ready for deployment. Manual intervention required.'"

                            update_result = await self._delegate_task("ServiceNowAgent", update_task, session_id)
                            results.append(f"**Step {i}b - ServiceNowAgent**: ✅ {update_result}")

                    elif agent_name == "ExecutorAgent":
                        # Deployment executed - add deployment update
                        job_id = context.get("job_id")
                        if any(keyword in result.lower() for keyword in ['success', 'started', 'job', 'running']):
                            context["deployment_success"] = True
                            if context.get("incident_number"):
                                job_info = f" Job ID {job_id} started successfully." if job_id else ""
                                update_task = f"Update incident {context['incident_number']} with work_notes 'Monte Carlo deployment to {namespace} namespace initiated successfully.{job_info} Monitor progress via Ansible AAP console.'"

                                update_result = await self._delegate_task("ServiceNowAgent", update_task, session_id)
                                results.append(f"**Step {i}b - ServiceNowAgent**: ✅ {update_result}")
                        else:
                            context["deployment_success"] = False

                else:
                    results.append(f"**Step {i} - {agent_name}**: ❌ Error - Agent not found")

            # Generate final summary
            status = "✅ SUCCESS" if context["deployment_success"] else "⚠️ ASSESSMENT ISSUES"
            tracking_info = []
            if context.get("incident_number"):
                tracking_info.append(f"ServiceNow: {context['incident_number']}")
            if context.get("job_id"):
                tracking_info.append(f"Job: {context['job_id']}")

            tracking = f" | {' | '.join(tracking_info)}" if tracking_info else ""

            header = f"🚀 **Practical Hybrid Workflow Complete**\n\n**Request:** {original_query}\n**Status:** {status}{tracking}\n**Steps:** {len(workflow)}\n\n"

            return header + "\n\n".join(results)

        except Exception as e:
            logger.error(f"Error executing workflow with progression: {e}")
            return f"Error executing workflow with progression: {str(e)}"

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Primary entrypoint: handles a user query using practical hybrid orchestration.
        """
        try:
            # Check if this should use dynamic workflow
            if self._should_use_dynamic_workflow(query):
                logger.info("Routing to practical hybrid workflow")
                return await self._execute_practical_hybrid_workflow(query, session_id)

            # For simple queries, handle directly
            return await self._handle_simple_query(query, session_id)

        except Exception as e:
            logger.error(f"ClaudeOrchestratorAgent error: {e}")
            return f"Orchestration error: {str(e)}"

    async def _handle_simple_query(self, query: str, session_id: str) -> str:
        """
        Handle simple queries by letting Claude answer directly.
        No workflows, no agents - just Claude responding naturally.
        """
        try:
            # Let Claude handle the simple query directly
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{
                    "role": "user", 
                    "content": f"Please answer this question directly and helpfully: {query}"
                }]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"Error in simple query handling: {e}")
            return f"I'm having trouble answering that question right now. Error: {str(e)}"


class ClaudeOrchestratorTaskManager(InMemoryTaskManager):
    """
    TaskManager wrapper for the practical hybrid orchestrator.
    Class name kept consistent for entry.py compatibility.
    """
    def __init__(self, agent: ClaudeOrchestratorAgent):
        super().__init__()
        self.agent = agent

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """Extract raw user text from JSON-RPC request."""
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Handle `tasks/send` calls with practical hybrid orchestration
        """
        logger.info(f"ClaudeOrchestratorTaskManager received task {request.params.id}")

        # Store or update the task record
        task = await self.upsert_task(request.params)

        # Extract the text and invoke practical hybrid orchestration
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
