# =============================================================================
# agents/planner_agent/agent.py - Claude Integration for Kubernetes Planning
# =============================================================================
# 🎯 Purpose:
# Monte Carlo deployment planning agent using Claude Sonnet 4 + Kubernetes MCP tools
# Follows the exact same pattern as your tell_time_agent but for cluster assessment
# =============================================================================

import os
import logging
import json
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    🎯 Kubernetes cluster planning agent for Monte Carlo deployment using Claude Sonnet 4
    Assesses cluster readiness using real Kubernetes MCP tools
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
        
        # Initialize MCP connector for Kubernetes tools
        self.mcp_tools = None
        self._initialize_mcp()
        
        logger.info(f"PlannerAgent initialized with Claude Sonnet 4 + Kubernetes MCP")
    
    def _initialize_mcp(self):
        """
        Initialize MCP connection - based on your test_mcp_connections.py pattern
        """
        try:
            from utilities.mcp.mcp_connect import MCPConnector
            self.mcp_connector = MCPConnector()
            self.mcp_tools = self.mcp_connector.get_tools()
            
            # Filter to only Kubernetes tools we'll actually use for planning
            self.k8s_tools = [
                'configuration_get',     # Get cluster config
                'namespaces_list',       # Check namespaces
                'pods_list',             # Overall cluster health  
                'pods_list_in_namespace', # Specific namespace check
                'resources_list',        # List resources by type
                'resources_get'          # Get specific resource details
            ]
            
            # Get available tool names (fix the server attribute access)
            available_tools = [tool.name for tool in self.mcp_tools]
            k8s_tools = [name for name in available_tools if name in self.k8s_tools]
            logger.info(f"Available Kubernetes MCP tools: {k8s_tools}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP: {e}")
            self.mcp_tools = []
    
    async def _call_k8s_tool(self, tool_name: str, args: dict = None) -> dict:
        """
        Call a Kubernetes MCP tool safely - following your test pattern
        """
        if not self.mcp_tools:
            return {"error": "MCP tools not initialized"}
            
        try:
            # Find the tool
            tool = next((t for t in self.mcp_tools if t.name == tool_name), None)
            if not tool:
                return {"error": f"Tool {tool_name} not found"}
            
            # Call the tool (based on your test_mcp_connections.py)
            result = await tool.run(args or {})
            return {"success": True, "data": result}
            
        except Exception as e:
            logger.error(f"Error calling {tool_name}: {e}")
            return {"error": str(e)}
    
    async def _assess_cluster_readiness(self, target_namespace: str) -> dict:
        """
        Assess cluster readiness for Monte Carlo deployment in specified namespace
        """
        assessment = {
            "cluster_config": None,
            "namespaces": None,
            "pods_status": None,
            "monte_carlo_namespace": None,
            "target_namespace": target_namespace,
            "recommendation": "NOT_READY",
            "issues": [],
            "next_steps": []
        }
        
        # 1. Check cluster configuration
        config_result = await self._call_k8s_tool('configuration_get')
        if config_result.get('success'):
            assessment["cluster_config"] = "HEALTHY"
            logger.info("✅ Cluster configuration accessible")
        else:
            assessment["issues"].append("Cannot access cluster configuration")
            assessment["next_steps"].append("Check kubeconfig and cluster connectivity")
        
        # 2. List all namespaces to check for target namespace
        ns_result = await self._call_k8s_tool('namespaces_list')
        if ns_result.get('success'):
            try:
                # Parse namespace data to look for target namespace
                ns_data = ns_result['data']
                namespaces = []
                
                # Handle different possible data formats
                if isinstance(ns_data, str):
                    ns_data = json.loads(ns_data)
                
                if isinstance(ns_data, list):
                    namespaces = [ns.get('name', ns) if isinstance(ns, dict) else str(ns) for ns in ns_data]
                elif isinstance(ns_data, dict) and 'items' in ns_data:
                    namespaces = [item.get('metadata', {}).get('name', '') for item in ns_data['items']]
                
                assessment["namespaces"] = namespaces
                
                # Check for target namespace
                if target_namespace in namespaces:
                    assessment["monte_carlo_namespace"] = "EXISTS"
                    logger.info(f"✅ {target_namespace} namespace found")
                else:
                    assessment["monte_carlo_namespace"] = "MISSING" 
                    assessment["issues"].append(f"{target_namespace} namespace does not exist")
                    assessment["next_steps"].append(f"Ansible playbook will create {target_namespace} namespace during deployment")
                
            except Exception as e:
                assessment["issues"].append(f"Error parsing namespace data: {e}")
        else:
            assessment["issues"].append("Cannot list namespaces")
            assessment["next_steps"].append("Check cluster permissions for namespace access")
        
        # 3. Check overall pod health
        pods_result = await self._call_k8s_tool('pods_list')
        if pods_result.get('success'):
            assessment["pods_status"] = "ACCESSIBLE"
            logger.info("✅ Pod listing successful - cluster responsive")
        else:
            assessment["issues"].append("Cannot list pods - cluster may be unhealthy")
            assessment["next_steps"].append("Check cluster health and pod permissions")
        
        # 4. If target namespace exists, check its pods
        if assessment["monte_carlo_namespace"] == "EXISTS":
            mc_pods_result = await self._call_k8s_tool('pods_list_in_namespace', {'namespace': target_namespace})
            if mc_pods_result.get('success'):
                logger.info(f"✅ {target_namespace} namespace is accessible and ready")
            else:
                assessment["issues"].append(f"{target_namespace} namespace exists but is not accessible")
        
        # 5. Make final recommendation
        if len(assessment["issues"]) == 0:
            assessment["recommendation"] = "READY"
        elif assessment["cluster_config"] and assessment["pods_status"]:
            # Cluster is healthy, missing namespace is normal and handled by Ansible
            assessment["recommendation"] = "READY_FOR_ANSIBLE_DEPLOYMENT"
        else:
            assessment["recommendation"] = "NOT_READY"
        
        return assessment
    
    async def invoke(self, query: str, session_id: str) -> str:
        """
        Handle user query for cluster planning - same interface as your tell_time_agent
        """
        try:
            # Check if this is a planning/assessment request
            planning_keywords = ['assess', 'ready', 'cluster', 'monte carlo', 'deployment', 'plan', 'namespace']
            is_planning_request = any(keyword.lower() in query.lower() for keyword in planning_keywords)
            
            if is_planning_request:
                # Check if user specified a namespace in their query
                namespace_specified = False
                target_namespace = None
                
                # Look for namespace in query (simple pattern matching)
                words = query.lower().split()
                for i, word in enumerate(words):
                    if word in ['namespace', 'ns'] and i + 1 < len(words):
                        target_namespace = words[i + 1]
                        namespace_specified = True
                        break
                    # Also check for direct namespace names in query
                    if 'monte-carlo' in word or 'montecarlo' in word:
                        target_namespace = word
                        namespace_specified = True
                        break
                
                if not namespace_specified:
                    # Ask for namespace first
                    return """To assess cluster readiness, please specify the target namespace:

Example: "Assess monte-carlo-risk-sim namespace" """
                
                # Simple cluster assessment for the specified namespace
                assessment = await self._assess_cluster_readiness(target_namespace)
                
                # Create simple system prompt 
                system_prompt = f"""You are a Kubernetes cluster planning agent.

Assessment for namespace: {target_namespace}
- Cluster Status: {assessment['cluster_config']}  
- Target Namespace: {assessment['monte_carlo_namespace']}
- Recommendation: {assessment['recommendation']}

Give a brief status report. If namespace is missing, note that Ansible will create it during deployment."""

            else:
                # Handle direct namespace input (like "monte-carlo-risk-sim")
                if query.strip() and not any(word in query.lower() for word in ['assess', 'check', 'ready']):
                    # Treat as namespace name
                    target_namespace = query.strip()
                    assessment = await self._assess_cluster_readiness(target_namespace)
                    
                    system_prompt = f"""You are a Kubernetes cluster planning agent.

Assessment for namespace: {target_namespace}
- Cluster Status: {assessment['cluster_config']}
- Target Namespace: {assessment['monte_carlo_namespace']}  
- Recommendation: {assessment['recommendation']}

Give a brief, simple status report. If namespace is missing, note that Ansible will handle creation during deployment."""
                else:
                    # General help
                    system_prompt = """I assess Kubernetes cluster readiness for Monte Carlo deployment.

Please specify a namespace to check, like: "monte-carlo-risk-sim" """
            
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
                return "I can help assess cluster readiness for Monte Carlo deployment. Please ask me to assess the cluster."
                
        except Exception as e:
            logger.error(f"PlannerAgent error: {e}")
            return f"Error assessing cluster: {str(e)}. Please check MCP connectivity and try again."
    
    async def stream(self, query: str, session_id: str):
        """
        Simulates streaming response - same interface as your tell_time_agent
        """
        result = await self.invoke(query, session_id)
        yield {
            "is_task_complete": True,
            "content": result
        }
