# =============================================================================
# agents/servicenow_agent/task_manager.py - ServiceNow Agent Task Manager
# =============================================================================
# 🎯 Purpose:
# Task manager for ServiceNow Agent - same pattern as other agents
# Handles JSON-RPC tasks/send requests for ITSM operations
# =============================================================================

import logging
from server.task_manager import InMemoryTaskManager
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, TaskStatus, TaskState, TextPart
from agents.servicenow_agent.agent import ServiceNowAgent

logger = logging.getLogger(__name__)


class ServiceNowTaskManager(InMemoryTaskManager):
    """
    TaskManager for ServiceNowAgent - same pattern as ExecutorAgent and PlannerAgent
    Handles incoming tasks and delegates to ServiceNowAgent.invoke()
    """

    def __init__(self, agent: ServiceNowAgent):
        super().__init__()
        self.agent = agent

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """Extract raw user text from JSON-RPC request - same as other agents"""
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Handle `tasks/send` calls for ServiceNow operations:
          1) Store incoming message in memory
          2) Invoke ServiceNowAgent to handle ITSM request
          3) Append the reply, mark task COMPLETED
          4) Return the full Task in the response
        """
        logger.info(f"ServiceNowTaskManager received task {request.params.id}")
        
        # Store or update the task record - same pattern
        task = await self.upsert_task(request.params)
        
        # Extract the text and invoke ServiceNow agent logic
        user_text = self._get_user_text(request)
        reply_text = await self.agent.invoke(user_text, request.params.sessionId)
        
        # Wrap reply in a Message object - same pattern
        msg = Message(role="agent", parts=[TextPart(text=reply_text)])
        
        # Safely append reply and update status under lock - same pattern
        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(msg)
        
        # Return the RPC response including the updated task - same pattern
        return SendTaskResponse(id=request.id, result=task)
