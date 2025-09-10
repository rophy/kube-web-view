"""
Example hook to authorize container log access based on OAuth2 session.

To be used with --logs-authorized-hook option

This example demonstrates different authorization strategies:
1. Check user groups/roles from OAuth2 session
2. Restrict access to production namespaces
3. Check resource labels for confidential data

See also https://kube-web-view.readthedocs.io/en/latest/oauth2.html
"""
import logging

logger = logging.getLogger(__name__)


async def logs_authorized(cluster, namespace: str, resource, session) -> bool:
    """
    Authorize access to container logs for a specific resource.
    
    Args:
        cluster: The Kubernetes cluster object
        namespace: Namespace of the resource
        resource: The Kubernetes resource object (Pod, Deployment, etc.)
        session: aiohttp session containing user info from OAuth2
    
    Returns:
        bool: True if authorized, False otherwise
    
    Usage: --logs-authorized-hook=hooks.logs_authorized
    """
    # Get user information from OAuth2 session
    # This assumes your oauth2_authorized_hook has stored user info in session
    user_email = session.get("user_email", "unknown")
    user_groups = session.get("groups", [])
    user_name = session.get("user_name", "unknown")
    
    logger.info(f"Checking log access for user {user_email} to {resource.kind}/{resource.name} in {namespace}")
    
    # Example 1: Check if user has specific role/group from OAuth2
    # Users must have 'logs-viewer' group to view any logs
    if "logs-viewer" not in user_groups and "admin" not in user_groups:
        logger.warning(f"User {user_email} lacks 'logs-viewer' or 'admin' group for {resource.name}")
        return False
    
    # Example 2: Restrict logs for production namespaces
    # Only users with 'prod-admin' group can view logs in production namespaces
    if namespace and namespace.startswith("prod-"):
        if "prod-admin" not in user_groups and "admin" not in user_groups:
            logger.warning(f"User {user_email} cannot view prod logs for {resource.name} in {namespace}")
            return False
    
    # Example 3: Check resource labels for confidential/sensitive data
    labels = resource.obj.get("metadata", {}).get("labels", {})
    
    # Check if resource is marked as confidential
    if labels.get("confidential") == "true":
        if "security-team" not in user_groups and "admin" not in user_groups:
            logger.warning(f"User {user_email} cannot view confidential logs for {resource.name}")
            return False
    
    # Example 4: Check if resource has specific security level
    security_level = labels.get("security-level", "low")
    if security_level in ["high", "critical"]:
        required_groups = {
            "high": ["security-team", "senior-devops", "admin"],
            "critical": ["security-team", "admin"]
        }
        if not any(group in user_groups for group in required_groups.get(security_level, [])):
            logger.warning(f"User {user_email} lacks required groups for {security_level} security level")
            return False
    
    # Example 5: Team-based access control
    # Check if user belongs to the team that owns the resource
    team_label = labels.get("team", "")
    if team_label:
        team_group = f"team-{team_label}"
        # Allow access if user is in the specific team or is an admin
        if team_group not in user_groups and "admin" not in user_groups:
            logger.warning(f"User {user_email} is not a member of {team_group}")
            return False
    
    # Example 6: Namespace-based team access
    # Map namespaces to teams
    namespace_teams = {
        "team-alpha": ["team-alpha", "platform-team"],
        "team-beta": ["team-beta", "platform-team"],
        "shared": ["team-alpha", "team-beta", "platform-team"],
    }
    
    if namespace in namespace_teams:
        allowed_teams = namespace_teams[namespace]
        if not any(team in user_groups for team in allowed_teams) and "admin" not in user_groups:
            logger.warning(f"User {user_email} not authorized for namespace {namespace}")
            return False
    
    # All checks passed
    logger.info(f"User {user_email} authorized to view logs for {resource.name}")
    return True


async def oauth2_authorized(data: dict, session):
    """
    Example OAuth2 authorization hook that stores user information in session.
    This should be used with --oauth2-authorized-hook option.
    
    This function extracts user information from the OAuth2 token response
    and stores it in the session for use by the logs_authorized hook.
    """
    import aiohttp
    
    token = data.get("access_token")
    
    # Example: Get user info from OAuth2 provider (adjust URL for your provider)
    # This example assumes a generic OAuth2 provider with a /userinfo endpoint
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(
            "https://oauth.example.com/userinfo",  # Replace with your OAuth2 provider's userinfo endpoint
            headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            if resp.status == 200:
                user_info = await resp.json()
                
                # Store user information in session
                # Adjust these fields based on your OAuth2 provider's response
                session["user_email"] = user_info.get("email", "unknown")
                session["user_name"] = user_info.get("name", "unknown")
                session["groups"] = user_info.get("groups", [])
                
                logger.info(f"OAuth2 login successful for {session['user_email']}")
                
                # Optional: Check if user is allowed to access the application at all
                allowed_domains = ["example.com", "example.org"]
                email_domain = session["user_email"].split("@")[-1]
                if email_domain not in allowed_domains:
                    logger.warning(f"User {session['user_email']} from unauthorized domain {email_domain}")
                    return False
                
                return True
            else:
                logger.error(f"Failed to get user info: HTTP {resp.status}")
                return False
    
    return False