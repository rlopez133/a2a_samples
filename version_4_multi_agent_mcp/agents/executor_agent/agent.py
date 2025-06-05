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
                logger.info(f"Raw job_data from AAP: {job_data}")
                logger.info(f"job_data type: {type(job_data)}")
                
                # Handle different response formats from MCP
                job_id = None
                if isinstance(job_data, dict):
                    job_id = job_data.get('id')
                elif hasattr(job_data, 'text'):
                    # Parse JSON from text response
                    try:
                        parsed_data = json.loads(job_data.text)
                        job_id = parsed_data.get('id')
                        job_data = parsed_data
                    except:
                        logger.error(f"Failed to parse job_data.text: {job_data.text}")
                elif isinstance(job_data, list) and len(job_data) > 0:
                    # Handle list response format
                    first_item = job_data[0]
                    if hasattr(first_item, 'text'):
                        try:
                            parsed_data = json.loads(first_item.text)
                            job_id = parsed_data.get('id')
                            job_data = parsed_data
                        except:
                            logger.error(f"Failed to parse list item text: {first_item.text}")
                
                logger.info(f"Extracted job_id: {job_id}")
                
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
            logger.info(f"Raw job_status response: {status_result}")
            
            if status_result.get('success'):
                status_data = status_result['data']
                logger.info(f"Status data type: {type(status_data)}")
                logger.info(f"Status data: {status_data}")
                
                # Handle different response formats
                parsed_status = None
                if isinstance(status_data, dict):
                    parsed_status = status_data
                elif hasattr(status_data, 'text'):
                    try:
                        parsed_status = json.loads(status_data.text)
                    except:
                        logger.error(f"Failed to parse status_data.text: {status_data.text}")
                elif isinstance(status_data, list) and len(status_data) > 0:
                    first_item = status_data[0]
                    if hasattr(first_item, 'text'):
                        try:
                            parsed_status = json.loads(first_item.text)
                        except:
                            logger.error(f"Failed to parse list item text: {first_item.text}")
                    elif isinstance(first_item, dict):
                        parsed_status = first_item
                
                if parsed_status:
                    return {"success": True, "status": parsed_status}
                else:
                    return {"success": False, "error": f"Unable to parse status data: {status_data}"}
            else:
                return {"success": False, "error": status_result.get('error')}
        except Exception as e:
            logger.error(f"Error checking job status: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
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
                    return f"""## ❌ Deployment Failed - Template Not Found

**Error:** MonteCarlo Application template not found in Ansible AAP
**Available Templates:** {', '.join(template_result.get('available_templates', []))}

**Troubleshooting Steps:**
1. Verify the 'MonteCarlo Application' job template exists in AAP
2. Check template permissions and availability
3. Contact Ansible AAP administrator if template is missing

**Error Details:** {template_result.get('error', 'Unknown error')}"""
                
                else:
                    # Template found, attempt deployment
                    template_id = template_result['template_id']
                    template_name = template_result['template_name']
                    
                    deploy_result = await self._execute_deployment(template_id, namespace)
                    
                    if deploy_result.get('started'):
                        job_id = deploy_result['job_id']
                        
                        # Get AAP URL from environment or use default
                        aap_url = os.getenv('AAP_URL', 'https://aap-aap.apps.cluster-zkwsn.dynamic.redhatworkshops.io')
                        job_url = f"{aap_url}/execution/jobs/playbook/{job_id}/output"
                        
                        return f"""## ✅ Deployment Started Successfully

**Ansible AAP Deployment Executor Report**
---

### 📋 Deployment Details
- **Template**: {template_name} (ID: {template_id})
- **Target Namespace**: `{namespace or 'default'}`
- **Status**: 🚀 **DEPLOYMENT STARTED**
- **Job ID**: `{job_id}`
- **Monitor URL**: {job_url}

---

### 🎯 Success Message
The Monte Carlo application deployment has been **successfully initiated** to the `{namespace or 'default'}` namespace.

**Tracking Information:**
- **Job ID**: `{job_id}`
- **Template ID**: {template_id}
- **Deployment Type**: Monte Carlo Risk Simulation Application
- **Monitor Progress**: {job_url}

You can monitor the deployment progress in real-time at: {job_url}

---

### 📊 Next Steps
- Monitor deployment status via Job ID: {job_id}
- Check progress at: {job_url}
- Verify application health post-deployment
- Check namespace resources and pod status

**Deployment tracking ID**: `{job_id}` ✨"""
                    else:
                        return f"""## ❌ Deployment Failed to Start

**Template:** {template_name} (ID: {template_id})
**Target Namespace:** {namespace or 'default'}
**Error:** {deploy_result.get('error')}

**Troubleshooting Steps:**
1. Check Ansible AAP connectivity
2. Verify template permissions
3. Review job template configuration
4. Check inventory and credential settings

**Support:** Contact Platform Engineering for assistance"""
            
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
                        if status_result.get('success'):
                            status_data = status_result['status']
                            job_status = status_data.get('status', 'Unknown')
                            job_started = status_data.get('started', 'N/A')
                            job_finished = status_data.get('finished', 'N/A')
                            
                            return f"""## 📊 Job Status Report

**Job ID:** {job_id}
**Status:** {job_status}
**Started:** {job_started}
**Finished:** {job_finished}

**Raw Details:** {status_data}

**AAP Monitor:** {os.getenv('AAP_URL', 'https://aap-aap.apps.cluster-zkwsn.dynamic.redhatworkshops.io')}/execution/jobs/playbook/{job_id}/output"""
                        else:
                            return f"""## ❌ Job Status Check Failed

**Job ID:** {job_id}
**Error:** {status_result.get('error')}

**Troubleshooting:**
- Verify job ID {job_id} exists in Ansible AAP
- Check AAP connectivity and MCP tools
- Review agent logs for detailed error information

**AAP Monitor:** {os.getenv('AAP_URL', 'https://aap-aap.apps.cluster-zkwsn.dynamic.redhatworkshops.io')}/execution/jobs/playbook/{job_id}/output"""
                    else:
                        return """## 📊 Job Status Check

To check job status, please provide a job ID:
- "Check job status 4"
- "Status of job 123"

I can also start new deployments:
- "Deploy Monte Carlo application"
- "Deploy Monte Carlo to monte-carlo-prod namespace" """
                else:
                    return """## 🚀 Ansible AAP Deployment Executor

I can execute Monte Carlo deployments using Ansible AAP job templates.

**Available Commands:**
- **Deploy:** "Deploy Monte Carlo application" 
- **Deploy to Namespace:** "Deploy Monte Carlo to namespace monte-carlo-staging"
- **Check Status:** "Check status of job 123"
- **List Jobs:** "Show recent jobs"

**Capabilities:**
- ✅ Execute Monte Carlo deployment jobs
- ✅ Monitor job status and progress
- ✅ Target specific namespaces
- ✅ Provide real-time job tracking

How can I help with your deployment?"""
                
        except Exception as e:
            logger.error(f"ExecutorAgent error: {e}")
            return f"## ❌ Deployment Executor Error\n\nError executing deployment: {str(e)}\n\n**Troubleshooting:**\n- Check AAP connectivity\n- Verify MCP tools are available\n- Review agent logs for details"
    
    async def stream(self, query: str, session_id: str):
        """
        Simulates streaming response - same interface as your tell_time_agent
        """
        result = await self.invoke(query, session_id)
        yield {
            "is_task_complete": True,
            "content": result
        }
