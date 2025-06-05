# =============================================================================
# agents/tell_time_agent/agent.py - Claude Integration (Clean)
# =============================================================================
# 🎯 Purpose:
# Replace Google ADK + Gemini with Anthropic + Claude Sonnet 4
# Keep the exact same interface as the original TellTimeAgent
# =============================================================================

import os
import logging
from datetime import datetime
import anthropic
from dotenv import load_dotenv

# Load environment variables 
load_dotenv()

logger = logging.getLogger(__name__)

class TellTimeAgent:
    """
    🕒 Simple agent that tells the current time using Claude Sonnet 4
    Replaces the original Gemini-based implementation but keeps same interface
    """
    
    # Keep the same supported content types as original
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        """
        Initialize Claude client instead of Google ADK components
        """
        # Initialize Claude client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        logger.info(f"TellTimeAgent initialized with Claude Sonnet 4")

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Handle a user query and return a response string.
        Same interface as original Gemini agent.
        
        Args:
            query (str): What the user said (e.g., "what time is it?")
            session_id (str): Helps group messages into a session
            
        Returns:
            str: Agent's reply with the current time
        """
        
        try:
            # Get current time
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Create system prompt similar to original instruction
            system_prompt = f"""You are a time-telling agent. 
            The current time is: {current_time}
            Reply with the current time in the format YYYY-MM-DD HH:MM:SS.
            Be helpful and friendly in your response."""
            
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": query
                }]
            )
            
            # Extract text from response
            if response.content and len(response.content) > 0:
                return response.content[0].text
            else:
                return f"The current time is: {current_time}"
                
        except Exception as e:
            logger.error(f"TellTimeAgent error: {e}")
            # Fallback to simple time response
            return f"The current time is: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    async def stream(self, query: str, session_id: str):
        """
        Simulates a "streaming" agent that returns a single reply.
        Keep same interface as original for compatibility.
        
        Yields:
            dict: Response payload with completion status and time
        """
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        yield {
            "is_task_complete": True,
            "content": f"The current time is: {current_time}"
        }
