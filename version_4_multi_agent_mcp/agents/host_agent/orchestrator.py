# =============================================================================
# agents/host_agent/claude_orchestrator.py
# =============================================================================
# 🎯 Purpose:
# Claude-based orchestrator that coordinates between A2A agents and MCP tools
# Enhanced with ServiceNow ITSM integration for deployment workflows
# =============================================================================

import uuid
import logging
import asyncio
import os
import re
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
    🤖 Claude-based OrchestratorAgent with ServiceNow ITSM integration:
      - Discovers A2A agents via DiscoveryClient → list of AgentCards
      - Connects to each A2A agent with AgentConnector
      - Discovers MCP servers via MCPConnector and loads MCP tools
      - Uses Claude Sonnet 4 to decide which tools to call
      - Routes user queries by picking and invoking the correct tool
      - Enhanced with 5-step ServiceNow deployment workflow
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

    def _should_use_servicenow_workflow(self, query: str) -> bool:
        """
        Determine if query should trigger the enhanced ServiceNow deployment workflow
        """
        deployment_keywords = [
            'deploy monte carlo',
            'monte carlo deploy',
            'deploy to',
            'deployment',
            'start deployment',
            'run deployment'
        ]

        query_lower = query.lower()
        return any(keyword in query_lower for keyword in deployment_keywords)

    def _extract_namespace(self, query: str) -> str:
        """
        Extract namespace from deployment query with enhanced pattern matching
        """
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
            r'deploy(?:ment)?\s+(?:to\s+)?(\S+)',  # "deploy to xyz" or "deployment xyz"
            r'namespace[:\s]+(\S+)',                # "namespace: xyz" or "namespace xyz"
            r'target[:\s]+(\S+)',                   # "target: xyz" or "target xyz"
            r'(?:to|into)\s+(\S+)',                 # "to xyz" or "into xyz"
        ]

        for pattern in patterns:
            match = re.search(pattern, query.lower())
            if match:
                namespace = match.group(1).strip('.,!?')
                logger.info(f"Found namespace via regex: {namespace}")
                return namespace

        # Default fallback
        logger.warning(f"Could not extract namespace from query: {query}")
        return 'unknown'

    def _extract_incident_number_from_response(self, response: str) -> str:
        """
        Extract incident number from ServiceNow agent response
        Looks for patterns like INC0010001, INC1234567, etc.
        """
        if not response:
            return None

        # Look for incident number pattern in response
        match = re.search(r'\b(INC\d+)\b', response.upper())
        if match:
            incident_number = match.group(1)
            logger.info(f"Extracted incident number: {incident_number}")
            return incident_number

        # Log if we can't find incident number
        logger.warning(f"Could not extract incident number from response: {response[:100]}...")
        return None

    async def _handle_servicenow_deployment_workflow(self, query: str, session_id: str) -> str:
        """
        Enhanced Monte Carlo deployment workflow with ServiceNow ITSM integration:
        1. ServiceNow → Create tracking incident
        2. PlannerAgent → Assess cluster readiness
        3. ServiceNow → Update incident with assessment
        4. ExecutorAgent → Deploy if ready
        5. ServiceNow → Close incident with results
        """
        try:
            # Extract namespace from query
            namespace = self._extract_namespace(query)

            # Step 1: Create ServiceNow incident for tracking
            logger.info("Step 1: Creating ServiceNow incident for deployment tracking")
            incident_response = await self._delegate_task("ServiceNowAgent", 
                f"Create incident with caller Roger Lopez, short description 'Deploy Monte Carlo Application to {namespace} Namespace', description 'Automated deployment workflow for Monte Carlo risk simulation application to {namespace} namespace via Ansible AAP. Includes cluster assessment, deployment execution, and status tracking.', category 'Software', urgency 2, impact 2", session_id)

            # Extract incident number from response
            incident_number = self._extract_incident_number_from_response(incident_response)

            if not incident_number:
                return f"""❌ **ServiceNow Integration Failed**

Failed to create tracking incident: {incident_response}

**Recommendation:** Check ServiceNow connectivity and retry deployment."""

            # Step 2: Get cluster assessment
            logger.info("Step 2: Getting cluster readiness assessment")
            assessment = await self._delegate_task("PlannerAgent",
                f"Assess cluster readiness for Monte Carlo deployment to {namespace}", session_id)

            # Step 3: Update incident with assessment results
            logger.info("Step 3: Updating ServiceNow incident with assessment")
            await self._delegate_task("ServiceNowAgent",
                f"Update incident {incident_number} with state 2, work_notes 'Cluster assessment completed. Results: {assessment[:200]}...'", session_id)

            # Check if deployment should proceed based on assessment
            ready_for_deployment = any(keyword in assessment.lower() for keyword in ['ready', 'healthy', 'accessible', 'available'])

            if ready_for_deployment:
                # Update incident before starting deployment
                await self._delegate_task("ServiceNowAgent",
                    f"Update incident {incident_number} with state 2, work_notes 'Starting deployment to {namespace} namespace'", session_id)
                
                # Step 4: Execute deployment using ExecutorAgent
                logger.info("Step 4: Executing deployment via ExecutorAgent")
                deployment_result = await self._delegate_task("ExecutorAgent", 
                    f"Deploy Monte Carlo application to {namespace} namespace", session_id)
                
                # Extract job ID for monitoring
                job_id_match = None
                job_id_pattern = r'Job ID.*?`(\d+)`'
                match = re.search(job_id_pattern, deployment_result)
                if match:
                    job_id_match = match.group(1)
                    logger.info(f"Extracted job ID for monitoring: {job_id_match}")
                
                # Step 5: Monitor job completion and update incident accordingly
                if job_id_match:
                    logger.info(f"Step 5: Monitoring job {job_id_match} for completion")
                    
                    # Check job status
                    job_status_result = await self._delegate_task("ExecutorAgent", 
                        f"Check status of job {job_id_match}", session_id)
                    
                    # Determine final status based on job completion
                    if any(keyword in job_status_result.lower() for keyword in ['successful', 'completed']):
                        logger.info("Step 5: Job completed successfully - closing incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} with state 6, comments 'Monte Carlo application successfully deployed to {namespace} namespace. Job {job_id_match} completed successfully. Application is running and ready for use.', work_notes 'Deployment completed successfully via A2A automation. Application running in {namespace} namespace.'", session_id)
                        final_status = "✅ SUCCESS - JOB COMPLETED"
                        next_steps = f"Application deployed successfully. Monitor in {namespace} namespace. ServiceNow incident {incident_number} closed."
                    elif any(keyword in job_status_result.lower() for keyword in ['failed', 'error']):
                        logger.info("Step 5: Job failed - updating incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} state to Work in Progress with work notes: Deployment job {job_id_match} failed. Details: {job_status_result[:200]}...", session_id)
                        final_status = "❌ DEPLOYMENT FAILED"
                        next_steps = f"Review job {job_id_match} logs. ServiceNow incident {incident_number} updated with failure details."
                    else:
                        # Job still running
                        logger.info("Step 5: Job still in progress - updating incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} state to Work in Progress with work notes: Deployment job {job_id_match} initiated successfully. Monitoring for completion.", session_id)
                        final_status = "🚀 DEPLOYMENT IN PROGRESS"
                        next_steps = f"Monitor job {job_id_match} completion. Update incident {incident_number} when job finishes."
                else:
                    # Fallback to original logic if no job ID found
                    if any(keyword in deployment_result.lower() for keyword in ['successfully', 'completed', 'running', 'success']) and 'started' not in deployment_result.lower():
                        logger.info("Step 5: Deployment successful - closing incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} with state 6, comments 'Monte Carlo application successfully deployed to {namespace} namespace. Deployment completed via Ansible AAP. Application is running and ready for use.', work_notes 'Deployment completed successfully via A2A automation. Application running in {namespace} namespace.'", session_id)
                        final_status = "✅ SUCCESS"
                        next_steps = f"Monitor application in {namespace} namespace. Check ServiceNow incident {incident_number} for complete audit trail."
                    elif 'started' in deployment_result.lower() and 'successfully' in deployment_result.lower():
                        logger.info("Step 5: Deployment initiated but not complete - updating incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} state to Work in Progress with work notes: Deployment initiated successfully. Job in progress. Awaiting completion status.", session_id)
                        final_status = "🚀 DEPLOYMENT INITIATED"
                        next_steps = f"Monitor deployment job completion. Update incident {incident_number} when job finishes. Check namespace {namespace} for pod status."
                    else:
                        logger.info("Step 5: Deployment failed - updating incident")
                        await self._delegate_task("ServiceNowAgent",
                            f"Update incident {incident_number} state to Work in Progress with work notes: Deployment failed. Error details: {deployment_result[:200]}...", session_id)
                        final_status = "❌ DEPLOYMENT FAILED"
                        next_steps = f"Review deployment logs and ServiceNow incident {incident_number}. Manual intervention required."

                return f"""🚀 **Monte Carlo Deployment Workflow Complete**

**ServiceNow Tracking:** {incident_number}
**Target Namespace:** {namespace}
**Final Status:** {final_status}

**📋 Workflow Summary:**
1. ✅ Created ServiceNow incident for tracking
2. ✅ Assessed cluster readiness: {assessment[:100]}...
3. ✅ Updated incident with assessment results
4. ✅ Executed deployment to {namespace}
5. ✅ Updated incident with final status

**🔍 Assessment Results:**
{assessment}

**⚙️ Deployment Results:**
{deployment_result}

**📝 Next Steps:**
{next_steps}"""

            else:
                # Assessment failed - don't proceed with deployment
                logger.info("Step 4: Cluster assessment failed - aborting deployment")
                await self._delegate_task("ServiceNowAgent",
                    f"Update incident {incident_number} state to Work in Progress and add work notes: Assessment failure - deployment aborted: {assessment[:200]}...", session_id)

                return f"""⚠️ **Monte Carlo Deployment Workflow - Assessment Failed**

**ServiceNow Tracking:** {incident_number}
**Target Namespace:** {namespace}
**Status:** ❌ ABORTED

**📋 Workflow Summary:**
1. ✅ Created ServiceNow incident for tracking
2. ❌ Cluster assessment failed
3. ✅ Updated incident with assessment failure
4. ⏹️ Deployment aborted (cluster not ready)

**⚠️ Assessment Results:**
{assessment}

**📝 Next Steps:**
1. Resolve cluster readiness issues identified in assessment
2. Check ServiceNow incident {incident_number} for detailed logs
3. Retry deployment once issues are resolved
4. Contact Platform Engineering if assistance needed

**Recommendation:** Do not proceed with deployment until cluster issues are resolved."""

        except Exception as e:
            logger.error(f"Error in enhanced deployment workflow: {e}")
            return f"""❌ **Deployment Workflow Error**

An error occurred during the deployment workflow: {str(e)}

**Troubleshooting Steps:**
1. Check all agent connectivity (ServiceNow, Planner, Executor)
2. Verify MCP tool availability
3. Check ServiceNow authentication
4. Review agent logs for detailed error information

**Support:** Contact Platform Engineering if the error persists."""

    def _build_system_prompt(self, session_id: str) -> str:
        """
        Build the system prompt for Claude with available tools and enhanced ServiceNow capabilities.
        """
        available_agents = self._get_available_agents()
        available_mcp_tools = self._get_available_mcp_tools()

        return f"""You are an orchestrator agent that coordinates between specialized agents and MCP tools with enhanced ServiceNow ITSM integration.

AVAILABLE A2A AGENTS:
{', '.join(available_agents)}

AVAILABLE MCP TOOLS:
{', '.join(available_mcp_tools)}

ENHANCED COORDINATION CAPABILITIES:
1. For deployment requests involving Monte Carlo applications:
   - Use the 5-step ServiceNow ITSM workflow:
     1. ServiceNow → Create tracking incident
     2. PlannerAgent → Assess cluster readiness
     3. ServiceNow → Update incident with assessment
     4. ExecutorAgent → Deploy if ready (or abort if not)
     5. ServiceNow → Close incident with final status

2. For assessment requests:
   - Delegate to PlannerAgent for cluster assessment

3. For ServiceNow operations:
   - Delegate to ServiceNowAgent for incident management

4. For direct tool needs:
   - Use MCP tools directly for specific operations

AGENT SPECIALIZATIONS:
- ServiceNowAgent: ITSM incident management, deployment tracking, audit trails
- PlannerAgent: Kubernetes cluster assessment, namespace checking
- ExecutorAgent: Ansible AAP deployment execution, job monitoring
- TellTimeAgent: Current time information
- GreetingAgent: Personalized greetings

ENHANCED WORKFLOW EXAMPLES:
User: "Deploy Monte Carlo to namespace-xyz"
→ Trigger 5-step ServiceNow workflow for full ITSM compliance

User: "Check cluster status for monte-carlo-prod"
→ Call PlannerAgent: "Assess monte-carlo-prod namespace"

User: "Create incident for deployment"
→ Call ServiceNowAgent: "Create incident for deployment"

Session ID: {session_id}

Analyze the user request and determine the best approach. For Monte Carlo deployments, use the enhanced ServiceNow workflow. Be specific about which agent to call and what message to send."""

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Primary entrypoint: handles a user query using Claude to orchestrate tools.
        Enhanced with ServiceNow workflow detection.
        """
        try:
            # Check if this should use the enhanced ServiceNow deployment workflow
            if self._should_use_servicenow_workflow(query):
                logger.info("Routing to enhanced ServiceNow deployment workflow")
                return await self._handle_servicenow_deployment_workflow(query, session_id)

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
            # For assessment requests, just use PlannerAgent
            if any(keyword in original_query.lower() for keyword in ['assess', 'check', 'status', 'ready']):
                return await self._delegate_task("PlannerAgent", original_query, session_id)

            # For ServiceNow requests, use ServiceNowAgent
            elif any(keyword in original_query.lower() for keyword in ['incident', 'servicenow', 'itsm', 'ticket']):
                return await self._delegate_task("ServiceNowAgent", original_query, session_id)

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
        DEPRECATED: Use _handle_servicenow_deployment_workflow instead
        """
        logger.warning("Using deprecated deployment workflow - consider using ServiceNow workflow")
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
        return f"""🤖 **Orchestrator Agent Ready**

I can help coordinate between these agents: {', '.join(available_agents)}

**Available Commands:**
- **Monte Carlo Deployment:** 'Deploy Monte Carlo to [namespace]' (uses 5-step ServiceNow workflow)
- **Cluster Assessment:** 'Assess cluster for [namespace]'
- **ServiceNow Operations:** 'Create incident for [purpose]' or 'Update incident [number]'
- **Current Time:** 'What time is it?'
- **Greetings:** 'Hello' or 'Greet me'

**Enhanced Features:**
- ✅ Full ServiceNow ITSM integration for deployments
- ✅ Automated incident tracking and audit trails
- ✅ Cluster readiness validation before deployment
- ✅ Coordinated workflow execution

**Your Query:** {query}

Please specify what you'd like me to help orchestrate!"""


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
