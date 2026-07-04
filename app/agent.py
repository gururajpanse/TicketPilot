# ruff: noqa
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

import asyncio
import datetime
import json
import os
import re
import sys
import time
from typing import Any, Literal, List
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.workflow import Workflow, node
from google.adk.events import RequestInput, Event
from google.adk.tools import AgentTool, McpToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.agents import Context
from google.genai import types

from app.config import config


# Define structured state schema for inter-node state sharing
class TicketState(BaseModel):
    ticket_id: str = ""
    title: str = ""
    description: str = ""
    priority: str = ""
    user: str = ""
    category: str = ""
    severity: str = ""
    
    # Internal routing and resolution flags
    deduplicated: bool = False
    parent_incident_id: str = ""
    resolution_status: str = "PENDING"  # PENDING, AUTO_RESOLVED, NEEDS_HUMAN_APPROVAL, ESCALATED, DEDUPLICATED, BLOCKED
    resolution_notes: str = ""
    kb_article_drafted: bool = False
    kb_article_content: str = ""
    
    # HITL approval state
    human_approved: bool = False
    human_rejected: bool = False
    human_feedback: str = ""
    
    # Security flags and logs
    security_check_passed: bool = True
    security_violation_reason: str = ""
    audit_log: List[dict] = []


# Helper action tools for updating ticket state
def set_ticket_details_action(ctx: Context, title: str, description: str, user: str, priority: str) -> str:
    """Sets the normalized ticket details in the state.

    Args:
        title: The clean, concise title of the ticket.
        description: The clean, detailed description of the ticket.
        user: The email address of the submitting user.
        priority: The priority of the ticket (Low, Medium, High, Critical).
    """
    ctx.state["title"] = title
    ctx.state["description"] = description
    ctx.state["user"] = user
    ctx.state["priority"] = priority
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "INGESTION",
        "severity": "INFO",
        "message": f"Normalized ticket details recorded for user: {user}."
    })
    return "Successfully recorded normalized ticket details."


def set_classification_action(ctx: Context, category: str, severity: str) -> str:
    """Sets the category and severity level of the ticket.

    Args:
        category: The IT category (network, access, hardware, software, billing, database, etc.).
        severity: The severity level (P1, P2, P3, P4).
    """
    ctx.state["category"] = category
    ctx.state["severity"] = severity
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "CLASSIFICATION",
        "severity": "INFO",
        "message": f"Classified as Category: {category}, Severity: {severity}."
    })
    return f"Successfully classified ticket as Category: {category}, Severity: {severity}."


def set_resolution_action(ctx: Context, resolution_notes: str, status: str) -> str:
    """Sets the resolution details and status for the current ticket.

    Args:
        resolution_notes: Detailed notes explaining the resolution or next actions.
        status: The final resolution status, must be 'AUTO_RESOLVED', 'NEEDS_HUMAN_APPROVAL', or 'ESCALATED'.
    """
    ctx.state["resolution_notes"] = resolution_notes
    ctx.state["resolution_status"] = status
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "RESOLUTION_PROPOSED",
        "severity": "INFO",
        "message": f"Proposed resolution with status '{status}': {resolution_notes}"
    })
    return f"Successfully set resolution notes and status to '{status}'."


def set_duplicate_action(ctx: Context, parent_incident_id: str) -> str:
    """Marks the ticket as a duplicate of a parent incident and links them.

    Args:
        parent_incident_id: The identifier of the parent incident (e.g., INC-4001).
    """
    ctx.state["deduplicated"] = True
    ctx.state["parent_incident_id"] = parent_incident_id
    ctx.state["resolution_status"] = "DEDUPLICATED"
    ctx.state["resolution_notes"] = f"Marked as duplicate of parent incident {parent_incident_id}."
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "DEDUPLICATION",
        "severity": "INFO",
        "message": f"Ticket linked to parent incident {parent_incident_id}."
    })
    return f"Ticket marked as duplicate of incident {parent_incident_id}."


def draft_kb_article_action(ctx: Context, article_content: str) -> str:
    """Drafts a knowledge base article for first-time resolutions.

    Args:
        article_content: The markdown content of the knowledge base article.
    """
    ctx.state["kb_article_drafted"] = True
    ctx.state["kb_article_content"] = article_content
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "KB_DRAFT",
        "severity": "INFO",
        "message": "Knowledge base article draft generated."
    })
    return "Knowledge Base article draft successfully created."


def assign_to_specialist_action(ctx: Context, specialist_queue: str, reasoning: str) -> str:
    """Assigns the ticket to a specialized support queue.

    Args:
        specialist_queue: The name of the queue (e.g., Network-Team, Access-Management, Billing-Ops, Hardware-Techs).
        reasoning: The rationale for assigning the ticket to this queue.
    """
    ctx.state["resolution_status"] = "ESCALATED"
    ctx.state["resolution_notes"] = f"Assigned to {specialist_queue}. Reason: {reasoning}"
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "QUEUE_ROUTING",
        "severity": "INFO",
        "message": f"Assigned to specialized queue {specialist_queue}."
    })
    return f"Ticket successfully routed to queue: {specialist_queue}."


def trigger_p1_alert_action(ctx: Context, incident_summary: str) -> str:
    """Triggers an urgent P1/critical incident alert to on-call engineers via Slack/PagerDuty.

    Args:
        incident_summary: A concise summary of the critical issue or ticket storm.
    """
    ctx.state["resolution_status"] = "ESCALATED"
    ctx.state["priority"] = "Critical"
    ctx.state["resolution_notes"] = f"CRITICAL P1 ALERT TRIGGERED: {incident_summary}."
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "P1_ESCALATION",
        "severity": "CRITICAL",
        "message": f"PagerDuty alert triggered: {incident_summary}"
    })
    return "On-call engineers have been paged. Critical alert triggered."


# Initialize Rate-Limited Gemini Model to prevent 429 ResourceExhausted errors
class RateLimitedGemini(Gemini):
    async def generate_content_async(self, *args, **kwargs):
        # 5-second delay to stay well under requests-per-minute rate limits
        await asyncio.sleep(5)
        async for response in super().generate_content_async(*args, **kwargs):
            yield response

    def generate_content(self, *args, **kwargs):
        time.sleep(5)
        return super().generate_content(*args, **kwargs)

model_instance = RateLimitedGemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(attempts=3),
)

# Instantiate MCP Toolset connecting to app/mcp_server.py stdio process
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
        )
    )
)

# 1. Ingestion Agent
ingestion_agent = LlmAgent(
    name="ingestion_agent",
    model=model_instance,
    instruction=(
        "You are an Ingestion Agent.\n"
        "Your task is to analyze raw tickets and normalize them into a standard, clean ticket schema.\n"
        "Call set_ticket_details_action to save the normalized ticket details (title, description, user, priority) into the state."
    ),
    tools=[set_ticket_details_action],
)

# 2. Classification Agent
classification_agent = LlmAgent(
    name="classification_agent",
    model=model_instance,
    instruction=(
        "You are a Classification Agent.\n"
        "Read the normalized ticket details. Assign an appropriate IT category (e.g. access, network, hardware, software, billing) "
        "and a severity level (P1 for critical outages, P2 for high priority, P3 for normal business, P4 for minor issues).\n"
        "Call set_classification_action to record your classification decision. You can lookup the user details via lookup_user_directory tool if needed."
    ),
    tools=[set_classification_action, mcp_toolset],
)

# 3. Deduplication Agent
deduplication_agent = LlmAgent(
    name="deduplication_agent",
    model=model_instance,
    instruction=(
        "You are a Deduplication Agent.\n"
        "Check if this ticket is a duplicate of a larger ongoing outage or ticket storm.\n"
        "Use the get_active_incidents tool to get current outage reports.\n"
        "Only mark as a duplicate if it matches the specific outage scope and description (e.g., broad network connection down, site offline in a specific region like US-East).\n"
        "Do NOT mark as a duplicate if it is an individual device error, local configuration profile corruption, or a local client settings issue, even if it mentions the same service (like VPN profile settings corrupt).\n"
        "If it is a duplicate, call set_duplicate_action with the parent incident ID (e.g., INC-8801).\n"
        "If it is a standalone unique ticket, state that no duplicate was found."
    ),
    tools=[set_duplicate_action, mcp_toolset],
)

# 4. Resolution Agent
resolution_agent = LlmAgent(
    name="resolution_agent",
    model=model_instance,
    instruction=(
        "You are a Resolution Agent.\n"
        "Review the ticket category, description, and severity (assigned priority).\n"
        "Do NOT check for global network outages or active incidents (e.g. AWS outage INC-8801). Outages and deduplication are already handled by the Deduplication Agent. Focus strictly on matching the ticket description to standard runbooks via search_runbooks tool.\n"
        "Use the search_runbooks tool to see if there is an existing runbook for this issue.\n"
        "For known low-risk issues (VPN reconnect, password reset, disk cleanup), apply standard runbooks:\n"
        "  - If the ticket has a High/Critical priority (or P1/P2 severity), OR involves manual config profile adjustments (like corrupt VPN profile files or config settings), you MUST call set_resolution_action with status='NEEDS_HUMAN_APPROVAL' and provide the proposed resolution notes.\n"
        "  - Otherwise, for simple, low-priority issues matching runbooks, call set_resolution_action with status='AUTO_RESOLVED' and draft a KB article if needed.\n"
        "For complex, high-risk or critical issues with no runbook, call set_resolution_action with status='ESCALATED'."
    ),
    tools=[set_resolution_action, draft_kb_article_action, mcp_toolset],
)

# 5. Routing Agent
routing_agent = LlmAgent(
    name="routing_agent",
    model=model_instance,
    instruction=(
        "You are a Routing Agent.\n"
        "For tickets that cannot be resolved automatically, assign them to the correct specialist queue/team.\n"
        "Call assign_to_specialist_action with the target queue (Network-Team, Access-Management, Billing-Ops, Hardware-Techs) "
        "and a clear explanation of why it is being routed there."
    ),
    tools=[assign_to_specialist_action, mcp_toolset],
)

# 6. Escalation Agent
escalation_agent = LlmAgent(
    name="escalation_agent",
    model=model_instance,
    instruction=(
        "You are an Escalation Agent.\n"
        "Evaluate the severity of the ticket. If the severity is P1 or indicates a massive system outage, "
        "call trigger_p1_alert_action to bypass the normal queue and page the on-call team immediately."
    ),
    tools=[trigger_p1_alert_action],
)

# Helper to read MOCK_MODE from environment
MOCK_MODE = os.environ.get("MOCK_MODE", "False").lower() in ("true", "1", "yes")

# Mock functions for local execution when MOCK_MODE is enabled to prevent free-tier 429 errors
def mock_ingestion_agent(ctx: Context) -> str:
    """Mock agent that normalizes raw ticket details and records them to state."""
    title = ctx.state.get("title", "")
    description = ctx.state.get("description", "")
    user = ctx.state.get("user", "unknown@company.com")
    priority = ctx.state.get("priority", "Medium")
    set_ticket_details_action(ctx, title, description, user, priority)
    return "Ticket successfully normalized and recorded by Ingestion Agent (Mock)."

def mock_classification_agent(ctx: Context) -> str:
    """Mock agent that assigns categories and severity levels to tickets."""
    title = ctx.state.get("title", "").lower()
    description = ctx.state.get("description", "").lower()
    
    category = "software"
    if "lock" in description or "password" in description or "login" in description:
        category = "access"
    elif "vpn" in description or "network" in description or "wifi" in description or "internet" in description:
        category = "network"
    
    # Determine severity
    severity = "P3"
    if "p1" in description or "critical" in description or "emergency" in description or "outage" in description:
        severity = "P1"
    elif "p2" in description or "high" in description or "vpn profile" in description:
        severity = "P2"
        
    set_classification_action(ctx, category, severity)
    return f"Classified ticket as Category: {category}, Severity: {severity} by Classification Agent (Mock)."

def mock_deduplication_agent(ctx: Context) -> str:
    """Mock agent that clusters duplicate outages while ignoring local configuration issues."""
    category = ctx.state.get("category", "")
    description = ctx.state.get("description", "").lower()
    
    # Deduplicate only if it's a generic VPN down network outage, not local settings profile corruptions
    if category == "network" and "vpn is down" in description:
        set_duplicate_action(ctx, parent_incident_id="INC-8801")
        return "Duplicate detected. Linked to parent incident INC-8801 (Mock)."
        
    return "No duplicate incident storm matched by Deduplication Agent (Mock)."

def mock_resolution_agent(ctx: Context) -> str:
    """Mock agent that applies runbooks or escalates/pauses based on ticket scope."""
    if ctx.state.get("deduplicated"):
        return "Ticket is duplicate, bypassing resolution (Mock)."
        
    description = ctx.state.get("description", "").lower()
    title = ctx.state.get("title", "").lower()
    combined = f"{title} {description}"
    
    if "lock" in combined or "password" in combined:
        # Test Case 1: Password reset reset runbook
        runbook_steps = "1. Verify user identity. 2. Trigger Active Directory password reset link."
        ctx.state["resolution_status"] = "AUTO_RESOLVED"
        ctx.state["resolution_notes"] = f"Applied Password Reset Runbook (RB-002):\n{runbook_steps}"
        ctx.state["kb_article_drafted"] = True
        ctx.state["kb_article_content"] = "Drafted KB article for Password reset first-time resolution."
        ctx.state["audit_log"].append({
            "timestamp": str(datetime.datetime.now()),
            "event": "RESOLUTION",
            "severity": "INFO",
            "message": "Ticket resolved automatically using standard runbook (Mock)."
        })
        return "Ticket successfully auto-resolved using standard runbook RB-002 (Mock)."
        
    if "profile settings corrupt" in combined or "vpn profile" in combined or "vpn configuration profile" in combined:
        # Test Case 3: Needs human approval
        ctx.state["resolution_status"] = "NEEDS_HUMAN_APPROVAL"
        ctx.state["resolution_notes"] = "Reinstall VPN client profile if corruption suspected. Requires operator confirmation."
        ctx.state["audit_log"].append({
            "timestamp": str(datetime.datetime.now()),
            "event": "RESOLUTION_PENDING",
            "severity": "WARNING",
            "message": "Ticket resolution requires human operator approval (Mock)."
        })
        return "Ticket resolution requires human approval. Routed to approval queue (Mock)."
        
    return "No matching runbooks found. Bypassing auto-resolution (Mock)."

def mock_routing_agent(ctx: Context) -> str:
    """Mock agent that routes unresolved tickets to specialist queues."""
    status = ctx.state.get("resolution_status", "PENDING")
    if status == "PENDING":
        category = ctx.state.get("category", "software")
        queue = "Network-Team" if category == "network" else "Access-Management"
        assign_to_specialist_action(ctx, specialist_queue=queue, reasoning="Routed by routing agent.")
        return f"Ticket routed to specialist queue: {queue} (Mock)."
    return "Routing not required (Mock)."

def mock_escalation_agent(ctx: Context) -> str:
    """Mock agent that alerts on critical P1 tickets."""
    severity = ctx.state.get("severity", "")
    if severity == "P1":
        trigger_p1_alert_action(ctx)
        return "Critical P1 alert pager triggered by Escalation Agent (Mock)."
    return "No escalation alert required (Mock)."


if MOCK_MODE:
    ingestion_tool = mock_ingestion_agent
    classification_tool = mock_classification_agent
    deduplication_tool = mock_deduplication_agent
    resolution_tool = mock_resolution_agent
    routing_tool = mock_routing_agent
    escalation_tool = mock_escalation_agent
else:
    ingestion_tool = AgentTool(agent=ingestion_agent)
    classification_tool = AgentTool(agent=classification_agent)
    deduplication_tool = AgentTool(agent=deduplication_agent)
    resolution_tool = AgentTool(agent=resolution_agent)
    routing_tool = AgentTool(agent=routing_agent)
    escalation_tool = AgentTool(agent=escalation_agent)

# 7. Main TicketPilot Orchestrator
triage_orchestrator_llm = LlmAgent(
    name="triage_orchestrator",
    model=model_instance,
    instruction=(
        "You are the main TicketPilot IT Service Desk Triage Orchestrator.\n"
        "You coordinate the end-to-end processing of support tickets by delegating to specialized sub-agents.\n"
        "Follow these steps in order:\n"
        "1. Call ingestion_agent to parse and normalize raw inputs.\n"
        "2. Call classification_agent to classify the ticket's category and severity.\n"
        "3. Call escalation_agent if classification reveals a P1/Critical issue, to trigger immediate pager notifications.\n"
        "4. Call deduplication_agent to check if this ticket is duplicate of a larger incident storm.\n"
        "5. If it is unique and not a duplicate, call resolution_agent to check if it matches runbooks for auto-resolution.\n"
        "6. If the resolution_agent sets the ticket status to NEEDS_HUMAN_APPROVAL, you MUST STOP immediately and do NOT call routing_agent. Only call routing_agent if the resolution_agent sets the status to PENDING or ESCALATED, or if no runbook was applicable.\n"
        "Ensure all decisions are logged, and return a summary of the orchestration decisions."
    ),
    tools=[
        ingestion_tool,
        classification_tool,
        deduplication_tool,
        resolution_tool,
        routing_tool,
        escalation_tool
    ]
)

@node
async def mock_orchestrator_node(ctx: Context, node_input: Any):
    # 1. Ingestion Agent
    mock_ingestion_agent(ctx)
    # 2. Classification Agent
    mock_classification_agent(ctx)
    # 3. Escalation Agent
    mock_escalation_agent(ctx)
    # 4. Deduplication Agent
    mock_deduplication_agent(ctx)
    
    # 5. Resolution Agent (only if not deduplicated)
    if not ctx.state.get("deduplicated"):
        mock_resolution_agent(ctx)
        
    # 6. Routing Agent (only if still pending)
    if ctx.state.get("resolution_status") == "PENDING":
        mock_routing_agent(ctx)
    
    return "Mock orchestration successfully completed locally with zero API requests."

# Conditionalize triage_orchestrator based on MOCK_MODE
if MOCK_MODE:
    triage_orchestrator = mock_orchestrator_node
else:
    triage_orchestrator = triage_orchestrator_llm


# Workflow function nodes
@node
async def security_checkpoint(ctx: Context, node_input: Any):
    title = ""
    description = ""
    user = "unknown@company.com"
    priority = "Medium"
    ticket_id = f"TICK-{datetime.datetime.now().strftime('%M%S')}"

    # Robust extraction of ticket content from Event, Content, or string inputs
    if hasattr(node_input, "output") and getattr(node_input, "output") is not None:
        node_input = node_input.output
    elif hasattr(node_input, "content") and getattr(node_input, "content") is not None:
        node_input = node_input.content

    if hasattr(node_input, "parts") and node_input.parts:
        parts_text = [p.text for p in node_input.parts if p.text]
        node_input = "".join(parts_text)

    # Try parsing string as JSON first to handle serialized dictionary payloads
    if isinstance(node_input, str):
        try:
            parsed = json.loads(node_input)
            if isinstance(parsed, dict):
                node_input = parsed
        except Exception:
            pass

    if isinstance(node_input, dict):
        title = node_input.get("title", "")
        description = node_input.get("description", "")
        user = node_input.get("user", "unknown@company.com")
        priority = node_input.get("priority", "Medium")
        ticket_id = node_input.get("ticket_id", ticket_id)
    elif isinstance(node_input, str):
        description = node_input
        title = "Chat Support Request"
    
    ctx.state["ticket_id"] = ticket_id
    ctx.state["title"] = title
    ctx.state["description"] = description
    ctx.state["user"] = user
    ctx.state["priority"] = priority
    ctx.state["audit_log"] = []
    ctx.state["security_check_passed"] = True

    audit_entry = {
        "timestamp": str(datetime.datetime.now()),
        "event": "INITIAL_TRIAGE",
        "severity": "INFO",
        "message": f"Triage started for ticket {ticket_id} submitted by {user}"
    }
    ctx.state["audit_log"].append(audit_entry)

    # 1. PII Scrubbing
    desc_scrubbed = description
    desc_scrubbed = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED_CARD]', desc_scrubbed)
    desc_scrubbed = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', desc_scrubbed)
    desc_scrubbed = re.sub(r'(?i)(password|passwd|secret|token|key)\s*[:=]\s*\S+', r'\1: [REDACTED_PASSWORD]', desc_scrubbed)
    
    if desc_scrubbed != description:
        ctx.state["description"] = desc_scrubbed
        ctx.state["audit_log"].append({
            "timestamp": str(datetime.datetime.now()),
            "event": "PII_REDACTION",
            "severity": "WARNING",
            "message": "PII scrubbed from ticket description."
        })

    # 2. Prompt Injection Check
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "you are now", 
        "override instructions", 
        "bypass safeguards", 
        "act as"
    ]
    has_injection = any(kw in description.lower() for kw in injection_keywords)
    if has_injection:
        ctx.state["security_check_passed"] = False
        ctx.state["security_violation_reason"] = "Prompt Injection Attempt Detected"
        ctx.state["resolution_status"] = "BLOCKED"
        ctx.state["audit_log"].append({
            "timestamp": str(datetime.datetime.now()),
            "event": "SECURITY_VIOLATION",
            "severity": "CRITICAL",
            "message": "Prompt injection detected in input prompt."
        })
        ctx.route = "SECURITY_EVENT"
        return "Security alert: Prompt injection detected."

    # 3. Domain Specific Rule: Corporate Email Verification
    email_domain = user.split("@")[-1] if "@" in user else ""
    if email_domain.lower() not in ["company.com", "corp.com", "internal.net"]:
        ctx.state["security_check_passed"] = False
        ctx.state["security_violation_reason"] = f"Non-corporate email domain: {user}"
        ctx.state["resolution_status"] = "BLOCKED"
        ctx.state["audit_log"].append({
            "timestamp": str(datetime.datetime.now()),
            "event": "SECURITY_VIOLATION",
            "severity": "CRITICAL",
            "message": f"Domain verification failed for user: {user}."
        })
        ctx.route = "SECURITY_EVENT"
        return f"Security alert: User domain '{email_domain}' is not authorized."

    ctx.route = "CLEAN"
    return {
        "ticket_id": ticket_id,
        "title": title,
        "description": desc_scrubbed,
        "user": user,
        "priority": priority
    }


@node
async def security_event_handler(ctx: Context, node_input: Any):
    ctx.state["resolution_status"] = "BLOCKED"
    ctx.state["resolution_notes"] = f"Ticket blocked due to security violation: {ctx.state.get('security_violation_reason')}"
    return {
        "status": "BLOCKED",
        "reason": ctx.state.get("security_violation_reason"),
        "ticket_id": ctx.state.get("ticket_id"),
        "message": "This request has been blocked by TicketPilot security policies."
    }


@node
async def post_orchestrator_router(ctx: Context, node_input: Any):
    status = ctx.state.get("resolution_status", "PENDING")
    if status == "NEEDS_HUMAN_APPROVAL":
        ctx.route = "NEEDS_APPROVAL"
        return "Ticket resolution requires human approval. Initiating approval flow."
    else:
        ctx.route = "FINAL"
        return "Ticket processing complete. Routing to final output."


@node(rerun_on_resume=True)
async def human_approval_node(ctx: Context, node_input: Any):
    int_id = "approval_id"
    if not ctx.state.get("human_approved") and not ctx.state.get("human_rejected"):
        if int_id in ctx.resume_inputs:
            user_response = ctx.resume_inputs[int_id]
            response_text = str(user_response).strip().lower()
            if "approve" in response_text or "yes" in response_text or "ok" in response_text:
                ctx.state["human_approved"] = True
                ctx.state["resolution_status"] = "AUTO_RESOLVED"
                ctx.state["human_feedback"] = response_text
                ctx.state["audit_log"].append({
                    "timestamp": str(datetime.datetime.now()),
                    "event": "HUMAN_APPROVAL",
                    "severity": "INFO",
                    "message": f"Human approved resolution. Feedback: {response_text}"
                })
            else:
                ctx.state["human_rejected"] = True
                ctx.state["resolution_status"] = "ESCALATED"
                ctx.state["human_feedback"] = response_text
                ctx.state["audit_log"].append({
                    "timestamp": str(datetime.datetime.now()),
                    "event": "HUMAN_APPROVAL",
                    "severity": "WARNING",
                    "message": f"Human rejected resolution/overrode decision. Escalating. Feedback: {response_text}"
                })
        else:
            yield RequestInput(
                interruptId=int_id,
                message=(
                    f"✋ [HUMAN IN THE LOOP APPROVAL REQUIRED]\n"
                    f"Ticket: {ctx.state.get('ticket_id')} - {ctx.state.get('title')}\n"
                    f"Proposed Resolution: {ctx.state.get('resolution_notes')}\n"
                    f"Do you approve this resolution? (Type YES to approve, or NO/rejection reason to override and escalate to Tier-3 support)"
                )
            )
            return
    yield "Approval completed."


@node
async def final_output_node(ctx: Context, node_input: Any):
    status = ctx.state.get("resolution_status", "PENDING")
    ticket_id = ctx.state.get("ticket_id")
    title = ctx.state.get("title")
    
    ctx.state["audit_log"].append({
        "timestamp": str(datetime.datetime.now()),
        "event": "TICKET_CLOSED",
        "severity": "INFO",
        "message": f"Ticket {ticket_id} processing ended with status: {status}"
    })

    return {
        "ticket_id": ticket_id,
        "title": title,
        "status": status,
        "category": ctx.state.get("category", ""),
        "severity": ctx.state.get("severity", ""),
        "deduplicated": ctx.state.get("deduplicated", False),
        "parent_incident_id": ctx.state.get("parent_incident_id", ""),
        "resolution_notes": ctx.state.get("resolution_notes", ""),
        "kb_article_drafted": ctx.state.get("kb_article_drafted", False),
        "kb_article_content": ctx.state.get("kb_article_content", ""),
        "audit_log": ctx.state.get("audit_log", [])
    }


# Declare the core ADK 2.0 Workflow Graph
workflow = Workflow(
    name="ticket_pilot_workflow",
    description="Orchestrates IT Ticket qualification, deduplication, resolution, security checking, and human verification.",
    state_schema=TicketState,
    edges=[
        ("START", security_checkpoint),
        (security_checkpoint, {"SECURITY_EVENT": security_event_handler, "CLEAN": triage_orchestrator}),
        (security_event_handler, final_output_node),
        (triage_orchestrator, post_orchestrator_router),
        (post_orchestrator_router, {"NEEDS_APPROVAL": human_approval_node, "FINAL": final_output_node}),
        (human_approval_node, final_output_node)
    ]
)

# App instance
app = App(
    root_agent=workflow,
    name="app",
)

# Maintain root_agent variable for backward compatibility with default test files
root_agent = workflow
