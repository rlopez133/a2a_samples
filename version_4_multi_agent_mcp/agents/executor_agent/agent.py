# =============================================================================
# agents/executor_agent/agent.py - Claude Integration for Ansible Execution
# =============================================================================
# 🎯 Purpose:
# Monte Carlo deployment executor using Claude Sonnet 4 + Ansible AAP MCP tools
# Follows the exact same pattern as your tell_time_agent but for deployment execution
# =============================================================================

import os
import logging
import json
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    🚀 Ansible AAP executor agent for Monte Carlo deployment using Claude Sonnet 4
    Executes deployment using real Ansible AAP MCP tools
    """
    
    # Keep the same supported content types as your pattern
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
    
    def __init__(self):
        """
        Initialize Claude client and MCP connector - following your pattern
        """
        # Initialize Claude client (same as your tell_time_agent)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
            
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Initialize MCP connector for Ansible tools
        self.mcp_tools = None
        self._initialize_mcp()
        
        logger.info(f"ExecutorAgent initialized with Claude Sonnet 4 + Ansible AAP MCP")
    
    def _initialize_mcp(self):
        """
        Initialize MCP connection - based on your test_mcp_connections.py pattern
        """
        try:
            from utilities.mcp.mcp_connect import MCPConnector
            self.mcp_connector = MCPConnector()
            self.mcp_tools = self.mcp_connector.get_tools()
            
            # Filter to only Ansible tools we'll use for execution
            self.ansible_tools = [
                'list_job_templates',    # Find MonteCarlo Application template
                'get_job_template',      # Get template details
                'run_job',               # Execute deployment
                'job_status',            # Monitor progress
                'job_logs',              # Get logs
                'list_recent_jobs'       # Check recent runs
            ]
            
            # Get available tool names
            available_tools = [tool.name for tool in self.mcp_tools]
            ansible_tools = [name for name in available_tools if name in self.ansible_tools]
            logger.info(f"Available Ansible AAP MCP tools: {ansible_tools}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP: {e}")
            self.mcp_tools = []
    
    async def _call_ansible_tool(self, tool_name: str, args: dict = None) -> dict:
        """
        Call an Ansible AAP MCP tool safely - following your test pattern
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
    
    async def _find_monte_carlo_template(self) -> dict:
        """
        Find the MonteCarlo Application job template in AAP
        """
        try:
            # List all job templates
            templates_result = await self._call_ansible_tool('list_job_templates')
            if not templates_result.get('success'):
                return {"error": "Cannot list job templates", "details": templates_result}
    
            templates_data = templates_result['data']
            logger.info(f"Raw templates_data type: {type(templates_data)}")
            logger.info(f"Raw templates_data: {templates_data}")
    
            # Handle different response formats
            if isinstance(templates_data, list):
                # If it's a list of TextContent, unwrap and parse it
                if len(templates_data) == 1 and hasattr(templates_data[0], 'text'):
                    logger.info("List contains a single TextContent object. Extracting JSON.")
                    templates_data = json.loads(templates_data[0].text)
                else:
                    logger.error("Unexpected list format in templates_data.")
                    return {"error": "Unexpected list format in templates_data."}
            elif hasattr(templates_data, 'text'):
                templates_data = json.loads(templates_data.text)
            elif hasattr(templates_data, 'content'):
                templates_data = json.loads(templates_data.content)
            elif isinstance(templates_data, str):
                templates_data = json.loads(templates_data)
            elif not isinstance(templates_data, dict):
                logger.error("Unknown response format.")
                return {"error": "Unknown format in templates_data."}
    
            monte_carlo_template = None
            available_templates = []
    
            if 'results' in templates_data:
                logger.info(f"Found {len(templates_data['results'])} templates")
                for template in templates_data['results']:
                    template_name = template.get('name', '')
                    available_templates.append(template_name)
                    logger.info(f"Checking template: {template_name}")
                    if template_name == 'MonteCarlo Application':
                        monte_carlo_template = template
                        logger.info(f"Found exact match: {template_name}")
                        break
                    elif 'MonteCarlo' in template_name or 'Monte Carlo' in template_name:
                        monte_carlo_template = template
                        logger.info(f"Found partial match: {template_name}")
                        break
    
            logger.info(f"Available templates: {available_templates}")
    
            if monte_carlo_template:
                return {
                    "found": True,
                    "template": monte_carlo_template,
                    "template_id": monte_carlo_template.get('id'),
                    "template_name": monte_carlo_template.get('name')
                }
            else:
                return {
                    "found": False,
                    "error": "MonteCarlo Application template not found in AAP",
                    "available_templates": available_templates
                }
    
        except Exception as e:
            logger.error(f"Error finding Monte Carlo template: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {"error": str(e)}
 
    async def _execute_deployment(self, template_id: int, namespace: str = None) -> dict:
        """
        Execute the MonteCarlo Application deployment
        """
        try:
            # Prepare extra variables if namespace specified
            extra_vars = {}
            if namespace:
                extra_vars['target_namespace'] = namespace
            
            # Run the job template
            job_result = await self._call_ansible_tool('run_job', {
                'template_id': template_id,
                'extra_vars': extra_vars if extra_vars else None
            })
            
            if job_result.get('success'):
                job_data = job_result['data']
                job_id = job_data.get('id') if isinstance(job_data, dict) else None
                
                return {
                    "started": True,
                    "job_id": job_id,
                    "job_data": job_data
                }
            else:
                return {"started": False, "error": job_result.get('error')}
                
        except Exception as e:
            logger.error(f"Error executing deployment: {e}")
            return {"started": False, "error": str(e)}
    
    async def _check_job_status(self, job_id: int) -> dict:
        """
        Check the status of a deployment job
        """
        try:
            status_result = await self._call_ansible_tool('job_status', {'job_id': job_id})
            if status_result.get('success'):
                return {"success": True, "status": status_result['data']}
            else:
                return {"success": False, "error": status_result.get('error')}
        except Exception as e:
            logger.error(f"Error checking job status: {e}")
            return {"success": False, "error": str(e)}
    
    async def invoke(self, query: str, session_id: str) -> str:
        """
        Handle user query for deployment execution - same interface as your tell_time_agent
        """
        try:
            # Check if this is a deployment request
            deploy_keywords = ['deploy', 'execute', 'run', 'monte carlo', 'montecarlo', 'start']
            is_deploy_request = any(keyword.lower() in query.lower() for keyword in deploy_keywords)
            
            if is_deploy_request:
                # Extract namespace if specified
                namespace = None
                words = query.lower().split()
                for i, word in enumerate(words):
                    if word in ['namespace', 'ns'] and i + 1 < len(words):
                        namespace = words[i + 1]
                        break
                    if 'monte-carlo' in word:
                        namespace = word
                        break
                
                # Find Monte Carlo template
                template_result = await self._find_monte_carlo_template()
                
                if not template_result.get('found'):
                    system_prompt = f"""You are an Ansible AAP deployment executor.

Template Search Results:
- Monte Carlo Template Found: NO
- Error: {template_result.get('error', 'Unknown error')}
- Available Templates: {template_result.get('available_templates', [])}

Explain that the MonteCarlo Application template was not found and list available templates."""
                
                else:
                    # Template found, attempt deployment
                    template_id = template_result['template_id']
                    template_name = template_result['template_name']
                    
                    deploy_result = await self._execute_deployment(template_id, namespace)
                    
                    if deploy_result.get('started'):
                        job_id = deploy_result['job_id']
                        system_prompt = f"""You are an Ansible AAP deployment executor.

Deployment Started Successfully:
- Template: {template_name} (ID: {template_id})
- Job ID: {job_id}
- Target Namespace: {namespace or 'default from playbook'}
- Status: DEPLOYMENT STARTED

Provide a success message with the job ID for tracking."""
                    else:
                        system_prompt = f"""You are an Ansible AAP deployment executor.

Deployment Failed to Start:
- Template: {template_name} (ID: {template_id})
- Error: {deploy_result.get('error')}

Explain the deployment failure and suggest troubleshooting steps."""
            
            else:
                # Handle job status checks or general queries
                if 'status' in query.lower() or 'job' in query.lower():
                    # Try to extract job ID
                    words = query.split()
                    job_id = None
                    for word in words:
                        if word.isdigit():
                            job_id = int(word)
                            break
                    
                    if job_id:
                        status_result = await self._check_job_status(job_id)
                        system_prompt = f"""You are an Ansible AAP deployment executor.

Job Status Check for Job ID {job_id}:
- Status Result: {status_result}

Report the current job status clearly."""
                    else:
                        system_prompt = """You are an Ansible AAP deployment executor.

I can deploy Monte Carlo applications using Ansible AAP. 

Commands:
- "Deploy Monte Carlo application" - Start deployment
- "Check job status 123" - Check specific job status
- "Deploy Monte Carlo to monte-carlo-prod namespace" - Deploy to specific namespace"""
                else:
                    system_prompt = """You are an Ansible AAP deployment executor for Monte Carlo applications.

I can execute Monte Carlo deployments using Ansible AAP job templates.

Example commands:
- "Deploy Monte Carlo application" 
- "Deploy Monte Carlo to namespace monte-carlo-staging"
- "Check status of job 123"

How can I help with your deployment?"""
            
            # Call Claude API - same pattern as your tell_time_agent
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": query
                }]
            )
            
            # Extract text from response - same as your pattern
            if response.content and len(response.content) > 0:
                return response.content[0].text
            else:
                return "I can help deploy Monte Carlo applications using Ansible AAP. Please specify your deployment request."
                
        except Exception as e:
            logger.error(f"ExecutorAgent error: {e}")
            return f"Error executing deployment: {str(e)}. Please check AAP connectivity and try again."
    
    async def stream(self, query: str, session_id: str):
        """
        Simulates streaming response - same interface as your tell_time_agent
        """
        result = await self.invoke(query, session_id)
        yield {
            "is_task_complete": True,
            "content": result
        }
