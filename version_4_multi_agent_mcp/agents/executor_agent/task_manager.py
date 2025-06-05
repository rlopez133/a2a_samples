# =============================================================================
# agents/executor_agent/task_manager.py - Updated for Claude
# =============================================================================
# 🎯 Purpose:
# Task manager for ExecutorAgent using Claude - exact same pattern as your tell_time_agent
# =============================================================================

import logging
from server.task_manager import InMemoryTaskManager
from agents.executor_agent.agent import ExecutorAgent
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, Task, TextPart, TaskStatus, TaskState

logger = logging.getLogger(__name__)


class AgentTaskManager(InMemoryTaskManager):
    """
    Task manager for ExecutorAgent using Claude
    Keeps the exact same name and interface as your tell_time_agent pattern
    """
    
    def __init__(self, agent: ExecutorAgent):
        """
        Initialize with the Claude-based ExecutorAgent
        Same interface as your tell_time_agent
        """
        super().__init__()
        self.agent = agent
    
    def _get_user_query(self, request: SendTaskRequest) -> str:
        """
        Get the user's text input from the request object.
        Same as your tell_time_agent implementation
        """
        return request.params.message.parts[0].text
    
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Handle `tasks/send` calls from other A2A agents.
        Same interface as your tell_time_agent, just using Claude for deployment instead of time
        """
        logger.info(f"ExecutorAgent processing task: {request.params.id}")
        
        # Step 1: Save the task using the base class helper
        task = await self.upsert_task(request.params)
        
        # Step 2: Get what the user asked
        query = self._get_user_query(request)
        
        # Step 3: Ask the Claude agent to respond with deployment execution
        result_text = await self.agent.invoke(query, request.params.sessionId)
        
        # Step 4: Turn the agent's response into a Message object
        agent_message = Message(
            role="agent",
            parts=[TextPart(text=result_text)]
        )
        
        # Step 5: Update the task state and add the message to history
        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(agent_message)
        
        # Step 6: Return a structured response back to the A2A client
        return SendTaskResponse(id=request.id, result=task)
