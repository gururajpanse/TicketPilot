# Submission Write-Up: TicketPilot (IT Service Desk Triage & Resolution Agent)

## Problem Statement
IT service desks are often overwhelmed by ticket storms (resulting from common network outages) and high volumes of repetitive, low-risk requests (like VPN issues or password resets). Manual triaging, classifying, checking for duplicates, applying standard runbooks, and routing tickets to specialist queues creates significant latency, raising operational costs and delaying resolution times. Furthermore, handling raw support inputs exposes security vulnerabilities, including PII exposure and prompt injection attacks designed to bypass helpdesk policies.

TicketPilot solves this problem by introducing a secure, autonomous multi-agent triage system that filters inputs, qualifications, clusters duplicates, auto-resolves standard runbook issues, and escalates critical incidents with full context for human review.

---

## Solution Architecture

TicketPilot utilizes a structured, deterministic directed acyclic graph (DAG) to orchestrate LLM agents, ensuring strict control flow, deterministic security checkpoints, and seamless human oversight.

```mermaid
graph TD
    START[Client Request] --> SEC[Security Checkpoint]
    SEC -->|Unsafe / Non-Corporate Domain| SEC_EV[Security Event Handler]
    SEC -->|Clean / Authorized| ORCH[Triage Orchestrator Agent]
    
    subgraph Sub-Agents (AgentTool Delegation)
        ORCH --> ING[Ingestion Agent]
        ORCH --> CLS[Classification Agent]
        ORCH --> ESC[Escalation Agent]
        ORCH --> DED[Deduplication Agent]
        ORCH --> RES[Resolution Agent]
        ORCH --> RTE[Routing Agent]
    end
    
    subgraph MCP Server Stdio Tools
        CLS & DED & RES & RTE --> MCP[MCP Toolset]
        MCP -->|lookup_user_directory| DIR[(User Directory)]
        MCP -->|get_active_incidents| INC[(Active Incidents)]
        MCP -->|search_runbooks| RUN[(Runbooks Database)]
        MCP -->|write_kb_article| WRI[(KB Publisher)]
    end

    ING -->|set_ticket_details_action| ST[ctx.state]
    CLS -->|set_classification_action| ST
    DED -->|set_duplicate_action| ST
    RES -->|set_resolution_action / draft_kb_article| ST
    RTE -->|assign_to_specialist_action| ST
    ESC -->|trigger_p1_alert_action| ST

    ORCH --> ROUTE{post_orchestrator_router}
    ROUTE -->|NEEDS_APPROVAL| HITL[Human Approval Node]
    ROUTE -->|FINAL| OUT[Final Output Node]
    
    HITL -->|yield RequestInput| USER[Human Operator ✋]
    USER -->|Resume Input| HITL
    HITL --> OUT
    SEC_EV --> OUT
    OUT --> END[Structured JSON Output]
```

---

## Concepts Used

1. **ADK 2.0 Workflow**: Configures the core execution graph in [agent.py](app/agent.py#L484-L501) with explicit conditional routing nodes (`security_checkpoint`, `triage_orchestrator`, `post_orchestrator_router`, `human_approval_node`, `final_output_node`).
2. **LlmAgent**: Defines 7 specialized LLM agents in [agent.py](app/agent.py#L182-L334) with unique instructions and system prompts tailored to distinct tasks.
3. **AgentTool**: Wraps sub-agents as tools in [agent.py](app/agent.py#L291-L296) so the orchestrator can dynamically delegate sub-tasks to specialized sub-agents.
4. **MCP Server**: Implements a dedicated Model Context Protocol (MCP) server in [mcp_server.py](app/mcp_server.py) connecting to local stdio, wired into agents via `McpToolset` in [agent.py](app/agent.py#L210-L219).
5. **Security Checkpoint**: Implements a deterministic node in [agent.py](app/agent.py#L338-L413) that scrubs inputs of PII, filters prompt injections, logs metadata, and enforces email domain constraints.
6. **Agents CLI & Scaffold**: Setup, initialized, and tested using the Google Agents CLI toolchain commands.

---

## Security Design

To prevent vulnerabilities, TicketPilot incorporates five security layers in [agent.py:security_checkpoint](app/agent.py#L338-L413):
- **PII Scrubbing**: Regex filters scrub Social Security Numbers (SSNs), Credit Card Numbers, and password credentials, preventing leakage to downstream LLMs.
- **Prompt Injection Defense**: Evaluates inputs against standard hijack patterns (e.g. `"ignore previous instructions"`, `"override safeguards"`). If an injection attempt is detected, the workflow routes to `security_event_handler`, blocking execution.
- **Domain Authorization Verification**: Blocks submissions from non-corporate email domains (anything outside `@company.com`, `@corp.com`, or `@internal.net`).
- **Structured Audit Logging**: Updates `ctx.state["audit_log"]` dynamically at every stage, compiling timestamps, event details, and severity markers (INFO, WARNING, CRITICAL).
- **Tool Sandbox**: Stdio-based MCP processes run locally and cannot write to external environments without authorized tool calls.

---

## MCP Server Design

The MCP server in [mcp_server.py](app/mcp_server.py) exposes four domain-specific tools over standard input/output transport:
1. `search_runbooks(query)`: Matches keywords (e.g., "vpn", "password", "disk cleanup") to retrieve deterministic resolution steps from `MOCK_RUNBOOKS`.
2. `get_active_incidents()`: Returns ongoing corporate outages (e.g., US-East network delays) to allow the deduplication agent to match and cluster recurring tickets.
3. `lookup_user_directory(username)`: Retrieves profile data, status (e.g., Active, Suspended), and department to verify access rights.
4. `write_kb_article(title, content)`: Simulates publishing newly discovered ticket resolutions to the corporate knowledge database.

---

## Human-in-the-Loop (HITL) Flow

A major design goal of TicketPilot is safety and policy compliance. Certain resolution actions (like restarting profiles or processing High-Priority requests) are marked as `NEEDS_HUMAN_APPROVAL` by the resolution agent.
When this status is reached:
1. The workflow transitions to [human_approval_node](app/agent.py#L427-L465).
2. The node yields a `RequestInput` event, pausing the execution thread and requesting user confirmation in the developer dashboard UI.
3. The workflow remains paused until a human operator replies (`YES` / `NO`).
4. Upon receiving input, the workflow resumes execution, updates state fields (`human_approved`, `human_feedback`), logs the audit event, and finishes processing.

---

## Demo Walkthrough

The demo includes three testing scenarios:
- **Scenario 1: Auto-Resolution**: A request from `alice@company.com` about an "Account Lockout" is ingestion-normalized, categorized as `access`/`P3`, matched via the MCP tool to `RB-002` (Password Lockout Runbook), auto-resolved, and a KB draft is generated.
- **Scenario 2: Outage Clustering**: A ticket reporting "VPN down in US East" from `bob@company.com` is classified as `network`/`P2`. The deduplication agent queries active incidents, identifies the active US-East-1 AWS outage (`INC-8801`), and maps the ticket to it, avoiding queue bloat.
- **Scenario 3: Human Verification**: A VPN profile corruption report classified as `network`/`P2` matches the reset runbook, but is routed to the human operator for confirmation. Once approved, the ticket is resolved.

---

## Impact / Value Statement
TicketPilot significantly reduces the burden on IT departments:
- **Reduces MTTR (Mean Time to Resolution)**: Resolves common repetitive issues instantly using runbooks.
- **De-clutters Queues**: Clusters incident storms into a single parent outage ticket.
- **Enhances Security**: Guarantees raw ticket data is cleaned of PII and protected from LLM prompt injections before processing.
- **Human Safeguards**: Combines automated speed with human accountability for high-risk operations.
