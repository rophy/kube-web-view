"""
Example hook to authorize container log access.

To be used with --logs-authorized-hook option

"""
import logging

async def logs_authorized(cluster, namespace: str, resource, session) -> bool:
    # Assume your oauth2_authorized_hook has stored user info in session
    email = session.get("email", "unknown")

    logger.info(
        f"Checking log access for user {email} to {resource.kind}/{resource.name} in {namespace}"
    )

    if namespace == "kube-system" return False
    return True
