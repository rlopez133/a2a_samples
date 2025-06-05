# =============================================================================
# agents/servicenow_agent/agent.py - Claude Integration for ServiceNow ITSM
# =============================================================================
# 🎯 Purpose:
# ServiceNow ITSM agent using Claude Sonnet 4 + ServiceNow MCP tools
# Enhanced to handle orchestrator commands with structured field updates
# =============================================================================

import os
import logging
import json
import re
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


class ServiceNowAgent:
    """
    🎫 ServiceNow ITSM agent for incident management using Claude Sonnet 4
    Manages incidents and ITSM workflows using real ServiceNow MCP tools
    Enhanced to handle orchestrator-style structured commands
    """

    # Keep the same supported content types as your pattern
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        """
        Initialize Claude client and MCP connector - following your pattern
        """
        # Initialize Claude client (same as your other agents)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"

        # Initialize MCP connector for ServiceNow tools
        self.mcp_tools = None
        self._initialize_mcp()

        logger.info(f"ServiceNowAgent initialized with Claude Sonnet 4 + ServiceNow MCP")

    def _initialize_mcp(self):
        """
        Initialize MCP connection - based on your existing pattern
        """
        try:
            from utilities.mcp.mcp_connect import MCPConnector
            self.mcp_connector = MCPConnector()
            self.mcp_tools = self.mcp_connector.get_tools()

            # Filter to only ServiceNow tools we'll use for ITSM
            self.servicenow_tools = [
                'create_incident',           # Create new incidents
                'update_incident',           # Update existing incidents
                'search_records',            # Search for records
                'get_record',                # Get specific record
                'perform_query',             # Perform queries
                'add_comment',               # Add customer comments
                'add_work_notes',            # Add internal work notes
                'natural_language_search',   # NL search capability
                'natural_language_update',   # NL update capability
                'update_script'              # Update scripts if needed
            ]

            # Get available tool names
            available_tools = [tool.name for tool in self.mcp_tools]
            snow_tools = [name for name in available_tools if name in self.servicenow_tools]
            logger.info(f"Available ServiceNow MCP tools: {snow_tools}")

        except Exception as e:
            logger.error(f"Failed to initialize MCP: {e}")
            self.mcp_tools = []

    async def _call_servicenow_tool(self, tool_name: str, args: dict = None) -> dict:
        """
        Call a ServiceNow MCP tool safely - following your existing pattern
        """
        if not self.mcp_tools:
            return {"error": "MCP tools not initialized"}

        try:
            # Find the tool
            tool = next((t for t in self.mcp_tools if t.name == tool_name), None)
            if not tool:
                return {"error": f"Tool {tool_name} not found"}

            # Call the tool
            result = await tool.run(args or {})
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"Error calling {tool_name}: {e}")
            return {"error": str(e)}

    def _parse_orchestrator_command(self, query: str) -> dict:
        """
        Parse structured commands from the orchestrator
        Handles commands like:
        - "Update incident INC123 with state 6, comments 'Success', work_notes 'Done'"
        - "Create incident with caller Roger Lopez, short description 'Deploy...'"
        """
        try:
            # Extract incident number
            incident_match = re.search(r'(INC\d+)', query.upper())
            incident_number = incident_match.group(1) if incident_match else None
            
            # Determine command type
            if query.lower().startswith('create incident'):
                return self._parse_create_command(query)
            elif query.lower().startswith('update incident') and incident_number:
                return self._parse_update_command(query, incident_number)
            elif query.lower().startswith('close incident') and incident_number:
                return self._parse_close_command(query, incident_number)
            else:
                return {"type": "unknown", "query": query}
                
        except Exception as e:
            logger.error(f"Error parsing orchestrator command: {e}")
            return {"type": "unknown", "query": query, "error": str(e)}

    def _parse_create_command(self, query: str) -> dict:
        """
        Parse create incident commands from orchestrator
        Example: "Create incident with caller Roger Lopez, short description 'Deploy Monte Carlo...'"
        """
        result = {"type": "create"}
        
        # Extract caller
        caller_match = re.search(r"caller\s+([^,]+)", query, re.IGNORECASE)
        if caller_match:
            result["caller_id"] = caller_match.group(1).strip()
        
        # Extract short description
        desc_match = re.search(r"short description\s+'([^']+)'", query, re.IGNORECASE)
        if desc_match:
            result["short_description"] = desc_match.group(1)
        
        # Extract description
        full_desc_match = re.search(r"description\s+'([^']+)'", query, re.IGNORECASE)
        if full_desc_match:
            result["description"] = full_desc_match.group(1)
        
        # Extract category
        category_match = re.search(r"category\s+'?([^,'\s]+)", query, re.IGNORECASE)
        if category_match:
            result["category"] = category_match.group(1)
        
        # Extract urgency
        urgency_match = re.search(r"urgency\s+(\d+)", query, re.IGNORECASE)
        if urgency_match:
            result["urgency"] = int(urgency_match.group(1))
        
        # Extract impact
        impact_match = re.search(r"impact\s+(\d+)", query, re.IGNORECASE)
        if impact_match:
            result["impact"] = int(impact_match.group(1))
        
        return result

    def _parse_update_command(self, query: str, incident_number: str) -> dict:
        """
        Parse update incident commands from orchestrator
        Example: "Update incident INC123 with state 6, comments 'Success', work_notes 'Completed'"
        """
        result = {"type": "update", "incident_number": incident_number}
        
        # Extract state
        state_match = re.search(r"state\s+(\d+)", query, re.IGNORECASE)
        if state_match:
            result["state"] = int(state_match.group(1))
        
        # Extract comments
        comments_match = re.search(r"comments\s+'([^']+)'", query, re.IGNORECASE)
        if comments_match:
            result["comments"] = comments_match.group(1)
        
        # Extract work notes
        work_notes_match = re.search(r"work_notes\s+'([^']+)'", query, re.IGNORECASE)
        if work_notes_match:
            result["work_notes"] = work_notes_match.group(1)
        
        # Fallback: if no structured fields, extract work notes from common patterns
        if not any(key in result for key in ["state", "comments", "work_notes"]):
            # Try old-style commands like "Update incident INC123 state to Work in Progress with work notes: Details"
            old_style_match = re.search(r"with work notes?:?\s*(.+)", query, re.IGNORECASE)
            if old_style_match:
                result["work_notes"] = old_style_match.group(1)
            elif "state to" in query.lower():
                state_text_match = re.search(r"state to\s+([^,]+)", query, re.IGNORECASE)
                if state_text_match:
                    state_text = state_text_match.group(1).strip()
                    # Convert text states to numbers
                    state_map = {
                        "new": 1,
                        "in progress": 2,
                        "work in progress": 2,
                        "on hold": 3,
                        "resolved": 6,
                        "closed": 7
                    }
                    result["state"] = state_map.get(state_text.lower(), 2)
        
        return result

    def _parse_close_command(self, query: str, incident_number: str) -> dict:
        """
        Parse close incident commands from orchestrator
        Example: "Close incident INC123 as resolved with comments: Success message"
        """
        result = {"type": "close", "incident_number": incident_number, "state": 6}  # Default to resolved
        
        # Extract resolution comments
        comments_match = re.search(r"with comments?:?\s*(.+)", query, re.IGNORECASE)
        if comments_match:
            result["comments"] = comments_match.group(1)
        
        # Check for specific close types
        if "resolved" in query.lower():
            result["state"] = 6
        elif "closed" in query.lower():
            result["state"] = 7
        
        return result

    async def _create_deployment_incident(self, create_data: dict) -> dict:
        """
        Create a ServiceNow incident for deployment tracking
        """
        try:
            # Prepare incident data with defaults
            incident_data = {
                "short_description": create_data.get("short_description", "Monte Carlo Deployment"),
                "description": create_data.get("description", "Automated deployment via A2A system"),
                "category": create_data.get("category", "Software").lower(),
                "urgency": create_data.get("urgency", 2),
                "impact": create_data.get("impact", 2),
                "caller_id": create_data.get("caller_id", "A2A System")
            }

            # Create the incident
            create_result = await self._call_servicenow_tool('create_incident', {
                'incident': incident_data
            })

            if create_result.get('success'):
                incident_response = create_result['data']

                # Handle different response formats
                if isinstance(incident_response, list) and len(incident_response) > 0:
                    if hasattr(incident_response[0], 'text'):
                        incident_data = json.loads(incident_response[0].text)
                    else:
                        incident_data = incident_response[0]
                elif hasattr(incident_response, 'text'):
                    incident_data = json.loads(incident_response.text)
                elif isinstance(incident_response, str):
                    incident_data = json.loads(incident_response)
                else:
                    incident_data = incident_response

                incident_number = incident_data.get('result', {}).get('number') or incident_data.get('number')

                return {
                    "created": True,
                    "incident_number": incident_number,
                    "incident_data": incident_data
                }
            else:
                return {"created": False, "error": create_result.get('error')}

        except Exception as e:
            logger.error(f"Error creating deployment incident: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {"created": False, "error": str(e)}

    async def _update_incident_structured(self, update_data: dict) -> dict:
        """
        Update incident with structured data from orchestrator
        """
        try:
            incident_number = update_data["incident_number"]
            updates = {}
            
            # Build update object
            if "state" in update_data:
                updates["state"] = update_data["state"]
            if "comments" in update_data:
                updates["comments"] = update_data["comments"]
            if "work_notes" in update_data:
                updates["work_notes"] = update_data["work_notes"]
            
            if not updates:
                return {"updated": False, "error": "No update fields provided"}
            
            # Call update_incident MCP tool
            update_result = await self._call_servicenow_tool('update_incident', {
                'number': incident_number,
                'updates': updates
            })

            if update_result.get('success'):
                return {"updated": True, "incident_number": incident_number, "updates": updates}
            else:
                return {"updated": False, "error": update_result.get('error')}

        except Exception as e:
            logger.error(f"Error updating incident: {e}")
            return {"updated": False, "error": str(e)}

    async def invoke(self, query: str, session_id: str) -> str:
        """
        Handle user query for ITSM operations with enhanced orchestrator command parsing
        """
        try:
            # Parse the command to understand what the orchestrator wants
            parsed_command = self._parse_orchestrator_command(query)
            logger.info(f"Parsed command: {parsed_command}")
            
            # Handle different command types
            if parsed_command["type"] == "create":
                # Create incident
                incident_result = await self._create_deployment_incident(parsed_command)
                
                if incident_result.get('created'):
                    incident_number = incident_result['incident_number']
                    return f"✅ Created ServiceNow incident **{incident_number}** for deployment tracking.\n\nIncident details recorded in ServiceNow for full audit trail."
                else:
                    return f"❌ Failed to create ServiceNow incident: {incident_result.get('error')}\n\nPlease check ServiceNow connectivity and try again."
            
            elif parsed_command["type"] == "update":
                # Update incident with structured data
                update_result = await self._update_incident_structured(parsed_command)
                
                if update_result.get('updated'):
                    incident_number = update_result['incident_number']
                    updates = update_result['updates']
                    update_summary = ", ".join([f"{k}: {v}" for k, v in updates.items()])
                    return f"✅ Updated incident **{incident_number}**\n\nUpdates applied: {update_summary}"
                else:
                    return f"❌ Failed to update incident: {update_result.get('error')}"
            
            elif parsed_command["type"] == "close":
                # Close incident
                update_result = await self._update_incident_structured(parsed_command)
                
                if update_result.get('updated'):
                    incident_number = update_result['incident_number']
                    state = parsed_command.get('state', 6)
                    state_name = "Resolved" if state == 6 else "Closed" if state == 7 else f"State {state}"
                    return f"✅ Incident **{incident_number}** closed as {state_name}\n\nFinal resolution recorded in ServiceNow."
                else:
                    return f"❌ Failed to close incident: {update_result.get('error')}"
            
            else:
                # Handle general ServiceNow requests (legacy support)
                return await self._handle_general_servicenow_request(query)

        except Exception as e:
            logger.error(f"ServiceNowAgent error: {e}")
            return f"❌ Error with ServiceNow operation: {str(e)}. Please check ServiceNow connectivity and try again."

    async def _handle_general_servicenow_request(self, query: str) -> str:
        """
        Handle general ServiceNow requests (non-orchestrator commands)
        """
        incident_keywords = ['incident', 'ticket', 'create', 'update', 'close', 'track', 'deployment', 'monte carlo']
        is_incident_request = any(keyword.lower() in query.lower() for keyword in incident_keywords)

        if is_incident_request:
            if any(word in query.lower() for word in ['search', 'find']):
                # Search for incidents
                search_criteria = self._extract_search_criteria(query)
                search_result = await self._search_incidents(search_criteria)

                if search_result.get('found'):
                    return f"🔍 Found incidents matching '{search_criteria}':\n\n{self._format_search_results(search_result.get('results'))}"
                else:
                    return f"❌ No incidents found for '{search_criteria}': {search_result.get('error', 'No matches')}"
            else:
                return """🎫 **ServiceNow ITSM Agent Ready**

I can help with incident management operations:

**Available Commands:**
- `Create incident for Monte Carlo deployment to [namespace]`
- `Update incident INC0010001 with [status/details]`
- `Close incident INC0010001 with [success/failed] status`
- `Search for incidents about [criteria]`

**Orchestrator Integration:**
I automatically handle structured commands from the orchestrator for seamless ITSM workflows.

How can I help with your ServiceNow operations?"""
        else:
            # General ServiceNow help
            return """🎫 **ServiceNow ITSM Specialist**

I manage ServiceNow incidents and ITSM workflows for Monte Carlo deployments.

**Common Operations:**
- **Create:** `Create deployment incident for monte-carlo-staging`
- **Update:** `Update incident INC0010001 with deployment progress`
- **Close:** `Close incident INC0010002 with success`
- **Search:** `Search for Monte Carlo incidents`

**Integration:** I work with the orchestrator to provide full ITSM compliance and audit trails for all deployments.

What ServiceNow operation can I help you with?"""

    async def _search_incidents(self, search_criteria: str) -> dict:
        """
        Search for incidents based on criteria
        """
        try:
            search_result = await self._call_servicenow_tool('search_records', {
                'query': search_criteria,
                'table': 'incident',
                'limit': 10
            })

            if search_result.get('success'):
                return {"found": True, "results": search_result['data']}
            else:
                return {"found": False, "error": search_result.get('error')}

        except Exception as e:
            logger.error(f"Error searching incidents: {e}")
            return {"found": False, "error": str(e)}

    def _extract_search_criteria(self, query: str) -> str:
        """Extract search criteria from search query"""
        words = query.lower().split()
        criteria_words = []

        skip_words = {'search', 'find', 'for', 'incidents', 'about', 'show', 'me', 'all', 'get', 'list'}
        for word in words:
            if word not in skip_words and len(word) > 2:
                criteria_words.append(word)

        return ' '.join(criteria_words) if criteria_words else 'Monte Carlo'

    def _format_search_results(self, results) -> str:
        """Format search results for display"""
        if not results:
            return "No incidents found."

        try:
            if isinstance(results, str):
                return results
            elif isinstance(results, list):
                formatted = []
                for idx, result in enumerate(results[:5]):
                    if isinstance(result, dict):
                        number = result.get('number', f'Result {idx+1}')
                        description = result.get('short_description', 'No description')
                        state = result.get('state', 'Unknown')
                        formatted.append(f"• **{number}**: {description} (State: {state})")
                    else:
                        formatted.append(f"• {str(result)}")
                return '\n'.join(formatted)
            else:
                return str(results)
        except Exception as e:
            logger.error(f"Error formatting search results: {e}")
            return f"Found results but couldn't format them: {str(results)[:200]}..."

    async def stream(self, query: str, session_id: str):
        """
        Simulates streaming response - same interface as other agents
        """
        result = await self.invoke(query, session_id)
        yield {
            "is_task_complete": True,
            "content": result
        }
