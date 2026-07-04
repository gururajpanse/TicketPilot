# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server using stdio transport
mcp = FastMCP("TicketPilot-MCP-Server")

# Sample Mock Databases
MOCK_RUNBOOKS = [
    {
        "id": "RB-001",
        "name": "VPN Connection Reset",
        "keywords": ["vpn", "anyconnect", "forticlient", "cisco", "connection failed"],
        "steps": "1. Reset VPN profile in settings. 2. Clear local browser DNS cache. 3. Re-verify MFA token. 4. Restart connection."
    },
    {
        "id": "RB-002",
        "name": "Password Reset / Lockout",
        "keywords": ["password", "lockout", "active directory", "login", "reset credentials"],
        "steps": "1. Check user identity in user directory. 2. Generate temporary password. 3. Set 'change on next login' flag. 4. Send secure link."
    },
    {
        "id": "RB-003",
        "name": "Disk Space Cleanup",
        "keywords": ["disk full", "disk space", "storage", "no space left", "out of space"],
        "steps": "1. Scan directory sizes. 2. Purge temp and package cache folders. 3. Run disk optimizer. 4. Verify free space > 15%."
    }
]

MOCK_INCIDENTS = [
    {
        "id": "INC-8801",
        "title": "AWS US-East-1 Network Outage",
        "severity": "P1",
        "status": "Active",
        "impact": "VPN and external access services are down for all users."
    },
    {
        "id": "INC-8802",
        "title": "Corporate Active Directory Domain Controller Delay",
        "severity": "P2",
        "status": "Active",
        "impact": "Ldap authentication queries are timing out intermittently."
    }
]

MOCK_USER_DIRECTORY = {
    "alice@company.com": {
        "name": "Alice Smith",
        "role": "Software Engineer",
        "department": "Engineering",
        "device": "MacBook Pro 16",
        "status": "Active"
    },
    "bob@company.com": {
        "name": "Bob Jones",
        "role": "HR Manager",
        "department": "Human Resources",
        "device": "ThinkPad T14",
        "status": "Active"
    },
    "charlie@company.com": {
        "name": "Charlie Brown",
        "role": "Accountant",
        "department": "Finance",
        "device": "Dell Latitude",
        "status": "Suspended"
    }
}


@mcp.tool()
def search_runbooks(query: str) -> str:
    """Searches historical IT runbooks for standard procedures matching the query terms.

    Args:
        query: Search keywords or error message (e.g. 'vpn connection failed', 'password locked').
    """
    query_lower = query.lower()
    matches = []
    for rb in MOCK_RUNBOOKS:
        matched = False
        for kw in rb["keywords"]:
            if kw in query_lower or query_lower in kw:
                matched = True
                break
        if matched or query_lower in rb["name"].lower():
            matches.append(rb)
    
    if not matches:
        return f"No standard runbooks found matching your query: '{query}'. Support engineer investigation required."
    
    response = "Matching Runbooks Found:\n"
    for m in matches:
        response += f"- [{m['id']}] {m['name']}\n  Steps: {m['steps']}\n"
    return response


@mcp.tool()
def get_active_incidents() -> str:
    """Retrieves all active high-severity IT incident storms and outages across the company."""
    if not MOCK_INCIDENTS:
        return "No active incident storms or outages reported at this time."
    
    response = "Active Incidents & Outages:\n"
    for inc in MOCK_INCIDENTS:
        response += f"- [{inc['id']}] {inc['title']} (Severity: {inc['severity']}, Status: {inc['status']})\n  Impact: {inc['impact']}\n"
    return response


@mcp.tool()
def lookup_user_directory(username: str) -> str:
    """Looks up a user's details, role, department, and active device in the corporate directory.

    Args:
        username: Corporate email address of the user (e.g. 'alice@company.com').
    """
    user_info = MOCK_USER_DIRECTORY.get(username.strip().lower())
    if not user_info:
        return f"User '{username}' was not found in the corporate directory."
    
    return (
        f"User Found:\n"
        f"- Name: {user_info['name']}\n"
        f"- Role: {user_info['role']}\n"
        f"- Department: {user_info['department']}\n"
        f"- Device: {user_info['device']}\n"
        f"- Status: {user_info['status']}"
    )


@mcp.tool()
def write_kb_article(title: str, content: str) -> str:
    """Publishes a new Knowledge Base article to the wiki database.

    Args:
        title: Title of the article.
        content: Markdown body content.
    """
    print(f"DEBUG: Publishing KB article: {title}", file=sys.stderr)
    return f"Successfully published Knowledge Base Article: '{title}' to internal portal."


if __name__ == "__main__":
    mcp.run(transport="stdio")
