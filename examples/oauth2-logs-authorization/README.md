# OAuth2 Logs Authorization Example

This example demonstrates how to use the `--logs-authorized-hook` option to control access to container logs based on OAuth2 authentication.

## Overview

The `logs_authorized` hook allows you to implement fine-grained authorization for container log access. This is particularly useful when:

- You want to restrict log access to sensitive applications
- Different teams should only see logs for their own resources
- Production logs should have restricted access
- Compliance requirements mandate log access controls

## Configuration

### 1. Basic Setup

```bash
kube-web-view \
  --show-container-logs \
  --oauth2-authorized-hook=hooks.oauth2_authorized \
  --logs-authorized-hook=hooks.logs_authorized
```

### 2. OAuth2 Configuration

Set the required OAuth2 environment variables:

```bash
export OAUTH2_AUTHORIZE_URL="https://oauth.example.com/authorize"
export OAUTH2_ACCESS_TOKEN_URL="https://oauth.example.com/token"
export OAUTH2_CLIENT_ID="your-client-id"
export OAUTH2_CLIENT_SECRET="your-client-secret"
```

### 3. Hook Implementation

The example `hooks.py` file demonstrates various authorization strategies:

#### Group-based Access Control
```python
# Users must have 'logs-viewer' group
if "logs-viewer" not in user_groups:
    return False
```

#### Namespace-based Restrictions
```python
# Production namespaces require 'prod-admin' group
if namespace.startswith("prod-"):
    if "prod-admin" not in user_groups:
        return False
```

#### Label-based Security
```python
# Check resource labels for security levels
if labels.get("confidential") == "true":
    if "security-team" not in user_groups:
        return False
```

#### Team-based Access
```python
# Users can only view logs for their team's resources
team_label = labels.get("team", "")
if team_label:
    team_group = f"team-{team_label}"
    if team_group not in user_groups:
        return False
```

## Integration with OAuth2 Providers

### GitHub Example

For GitHub OAuth2, modify the `oauth2_authorized` function:

```python
async def oauth2_authorized(data: dict, session):
    token = data["access_token"]
    async with aiohttp.ClientSession() as http_session:
        # Get user info
        async with http_session.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}"}
        ) as resp:
            user_info = await resp.json()
            session["user_email"] = user_info["email"]
            session["user_name"] = user_info["login"]
        
        # Get user's teams/orgs
        async with http_session.get(
            "https://api.github.com/user/teams",
            headers={"Authorization": f"token {token}"}
        ) as resp:
            teams = await resp.json()
            session["groups"] = [team["slug"] for team in teams]
    
    return True
```

### Google OAuth Example

For Google OAuth2:

```python
async def oauth2_authorized(data: dict, session):
    token = data["access_token"]
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            user_info = await resp.json()
            session["user_email"] = user_info["email"]
            session["user_name"] = user_info["name"]
            # Google groups would need additional API calls
            session["groups"] = []
    
    return True
```

## Kubernetes Resource Labels

To use label-based authorization, label your resources appropriately:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sensitive-app
  labels:
    team: security
    confidential: "true"
    security-level: high
```

## Testing

1. Deploy a test application with appropriate labels:
```bash
kubectl create deployment test-app --image=nginx
kubectl label deployment test-app team=alpha security-level=low
```

2. Create a sensitive application:
```bash
kubectl create deployment sensitive-app --image=nginx
kubectl label deployment sensitive-app team=security confidential=true security-level=high
```

3. Access the logs page for each deployment and verify that access is properly controlled based on your OAuth2 session.

## Security Considerations

1. **Session Security**: The OAuth2 session data is stored in encrypted cookies. Ensure `SESSION_SECRET_KEY` is properly set.

2. **Token Validation**: Always validate OAuth2 tokens with your provider's API rather than trusting client-provided data.

3. **Audit Logging**: The hook logs all authorization decisions. Ensure these logs are properly collected and monitored.

4. **Default Deny**: The example implements a default-deny approach - access is only granted if explicitly allowed.

5. **Regular Review**: Regularly review and update authorization rules as team structures and security requirements change.

## Troubleshooting

### Logs Not Showing Despite Authorization

Check that `--show-container-logs` is enabled in addition to the authorization hook.

### Session Data Not Available

Ensure the `oauth2_authorized_hook` is properly storing user data in the session before the `logs_authorized_hook` is called.

### Debug Logging

Enable debug logging to see authorization decisions:

```bash
kube-web-view --debug ...
```

## Advanced Use Cases

### Time-based Access

Add time-based restrictions:

```python
from datetime import datetime

# Only allow log access during business hours
current_hour = datetime.now().hour
if current_hour < 8 or current_hour > 18:
    if "on-call" not in user_groups:
        return False
```

### Rate Limiting

Implement rate limiting per user:

```python
# Store in session or external cache
access_count = session.get(f"log_access_count_{user_email}", 0)
if access_count > 100:  # Max 100 log views per session
    return False
session[f"log_access_count_{user_email}"] = access_count + 1
```

### External Authorization Service

Query an external service for authorization:

```python
async with aiohttp.ClientSession() as http_session:
    async with http_session.post(
        "https://authz.example.com/check",
        json={
            "user": user_email,
            "resource": f"{namespace}/{resource.name}",
            "action": "view-logs"
        }
    ) as resp:
        result = await resp.json()
        return result.get("allowed", False)
```