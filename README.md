# 🎫 TicketPilot — Autonomous IT Service Desk Triage & Resolution Agent

> An autonomous, secure IT service desk triage and resolution agent built with **Google ADK 2.0** and Gemini that automatically ingests, classifies, deduplicates, and resolves incoming support requests through a graph-based workflow — combining LLM intelligence, security guardrails, custom MCP tools, and human-in-the-loop oversight.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Google ADK 2.0](https://img.shields.io/badge/Google%20ADK-2.0-4285F4.svg)](https://adk.dev/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## 🎨 Assets

![TicketPilot Cover Banner](assets/cover_page_banner.png)

![TicketPilot Architecture Diagram](assets/architecture_diagram.png)

---

## ✨ Features

- **🛡️ Secure Ingestion** — Checks inputs for prompt injections, scrubs PII (Credit Cards, SSNs, Passwords), and enforces corporate email domain authorization.
- **🔄 Graph-Based Control Flow** — Orchestrates support requests using a directed graph with custom routing nodes implemented via the ADK workflow.
- **🤖 Multi-Agent Delegation** — Leverages a main triage orchestrator delegating dynamically to 6 sub-agents (Ingestion, Classification, Deduplication, Resolution, Routing, Escalation).
- **🔌 Model Context Protocol (MCP)** — Integrated MCP server running on local stdio transport to query user directory profiles, active incident storms, and search runbooks.
- **👤 Human-in-the-Loop (HITL)** — High-priority requests and manual configuration adjustments automatically pause for manager approval.
- **⏱️ API Quota Protection (Rate-Limiting)** — Custom `RateLimitedGemini` decorator subclassing that delays requests to prevent free-tier 429 quota exhaustion.

---

## 🏗️ Architecture

TicketPilot organizes its workflows using a deterministic directed acyclic graph (DAG) implemented in the ADK workflow runner:

```mermaid
graph TD
    START[Client Request] --> SEC[Security Checkpoint]
    SEC -->|Unsafe / Non-Corporate Domain| SEC_EV[Security Event Handler]
    SEC -->|Clean / Authorized| ORCH[Triage Orchestrator Agent]
    
    subgraph "Sub-Agents (AgentTool Delegation)"
        ORCH --> ING[Ingestion Agent]
        ORCH --> CLS[Classification Agent]
        ORCH --> ESC[Escalation Agent]
        ORCH --> DED[Deduplication Agent]
        ORCH --> RES[Resolution Agent]
        ORCH --> RTE[Routing Agent]
    end
    
    subgraph "MCP Server Stdio Tools"
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

    style START fill:#4285F4,stroke:#333,color:#fff
    style SEC fill:#FBBC04,stroke:#333,color:#000
    style SEC_EV fill:#EA4335,stroke:#333,color:#fff
    style ORCH fill:#4285F4,stroke:#333,color:#fff
    style HITL fill:#9C27B0,stroke:#333,color:#fff
    style USER fill:#9C27B0,stroke:#333,color:#fff
    style OUT fill:#607D8B,stroke:#333,color:#fff
    style END fill:#34A853,stroke:#333,color:#fff
```

---

## 📁 Project Structure

```
ticket-pilot/
├── app/
│   ├── agent.py                 # Main workflow graph & agent nodes
│   ├── config.py                # Configuration parsing & environment variables
│   ├── mcp_server.py            # Model Context Protocol stdio tools
│   ├── agent_runtime_app.py     # FastAPI server entry point
│   └── app_utils/
│       ├── telemetry.py         # OpenTelemetry instrumentation
│       └── typing.py            # Shared data types
├── assets/                      # Professional images for documentation
│   ├── architecture_diagram.png # 16:9 Agent graph flow diagram
│   └── cover_page_banner.png    # 16:9 Premium banner
├── tests/                       # Unit & integration testing suites
│   ├── unit/
│   └── integration/
├── Makefile                     # Build & run automation
├── pyproject.toml               # Dependencies & tooling configuration
└── DEMO_SCRIPT.txt              # Timed demo presentation guide
```

---

## ⚙️ Installation

Clone the repository and install the dependencies:
```bash
git clone https://github.com/gururajpanse/TicketPilot.git
cd ticket-pilot
make install
```

---

## 🔒 Configuration (.env)

Setup your environment configurations:

1. Copy the template:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and add your Gemini API Key:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key_here
   GOOGLE_GENAI_USE_VERTEXAI=False
   GEMINI_MODEL=gemini-3.1-flash-lite
   MOCK_MODE=False
   ```
   *(Ensure `MOCK_MODE=True` is enabled if you have exhausted your API key daily free-tier quota, which runs all sub-agents locally in python).*

---

## 🚀 Running the Project

Launch the Dev Playground UI:
```bash
make playground
```
*(Opens the ADK testing web application at http://localhost:18081)*

Start local API Server mode:
```bash
make run
```

Run unit and integration tests:
```bash
make test
```

---

## 💡 Usage

### Running an Analysis
1. Open the Dev Playground UI at http://localhost:18081.
2. Click **New Session** at the top.
3. Paste a ticket query in JSON or raw text. Example:
   ```json
   {
     "title": "VPN profile settings corrupt",
     "description": "My VPN configuration profile appears to be corrupt, need a new profile config file.",
     "user": "alice@company.com",
     "priority": "High"
   }
   ```
4. If the request requires human review, the agent will pause. Simply type `YES` in the response box to proceed.

### Test Case Scenarios

#### Test Case 1: Auto-Resolution (Access / Password Lockout)
- **Input (JSON)**:
  ```json
  {
    "title": "Help! Account locked out after multiple attempts",
    "description": "I cannot login to my account. My password was wrong. Please reset it.",
    "user": "alice@company.com",
    "priority": "Medium"
  }
  ```
- **Expected Path**: `security_checkpoint` passes successfully. `triage_orchestrator` classifies the ticket as `access`/`P3`. `deduplication_agent` finds no duplicate incident storms. `resolution_agent` searches the MCP runbooks, matches the **Password Reset** runbook (`RB-002`), applies the steps, drafts a KB article, and closes the ticket.
- **Check**: The UI should show the ticket status as `AUTO_RESOLVED`, `resolution_notes` listing reset steps, and `kb_article_drafted: true`.

#### Test Case 2: Outage Deduplication (Network / Outage Duplicate)
- **Input (JSON)**:
  ```json
  {
    "title": "VPN is down",
    "description": "I cannot connect to the corporate VPN from US East. Getting connection failed errors.",
    "user": "bob@company.com",
    "priority": "High"
  }
  ```
- **Expected Path**: `security_checkpoint` passes. `triage_orchestrator` classifies it as `network`/`P2`. `deduplication_agent` queries the MCP tool `get_active_incidents()`, matches the description with active outage `INC-8801` (AWS US-East-1 Network Outage), calls `set_duplicate_action`, and clusters it.
- **Check**: The UI should output `deduplicated: true` and `parent_incident_id: "INC-8801"`.

#### Test Case 3: Human-in-the-Loop Approval (VPN Profile Corruption)
- **Input (JSON)**:
  ```json
  {
    "title": "VPN profile settings corrupt",
    "description": "My VPN configuration profile appears to be corrupt, need a new profile config file.",
    "user": "alice@company.com",
    "priority": "High"
  }
  ```
- **Expected Path**: Classifies as `network`/`P2`. `deduplication_agent` checks and finds no outage duplicate. `resolution_agent` matches the **VPN Connection Reset** runbook (`RB-001`), but because the ticket has a `High` priority and involves config adjustments, it triggers the `NEEDS_HUMAN_APPROVAL` status. The workflow pauses at `human_approval_node` and yields a `RequestInput` event.
- **Check**: The dashboard UI will display a prompt asking you to approve the resolution. Reply with **`YES`** to resume the workflow. The ticket closes with `AUTO_RESOLVED` status and the `human_approved: true` state flag saved in the audit logs.

---

## 📊 Example Output

When a ticket is successfully resolved and approved by the human operator, TicketPilot compiles a structured state output:

```json
{
  "ticket_id": "TICK-2900",
  "title": "VPN profile settings corrupt",
  "status": "AUTO_RESOLVED",
  "category": "network",
  "severity": "P2",
  "deduplicated": false,
  "parent_incident_id": "",
  "resolution_notes": "The user has a corrupt VPN profile. Following standard procedure RB-001: 1. Reset VPN profile in settings. 2. Clear local browser DNS cache. 3. Re-verify MFA token. 4. Restart connection. Since this involves manual config profile adjustments, it requires human approval per protocol.",
  "kb_article_drafted": false,
  "kb_article_content": "",
  "audit_log": [
    {
      "timestamp": "2026-07-05 01:29:00.800259",
      "event": "INITIAL_TRIAGE",
      "severity": "INFO",
      "message": "Triage started for ticket TICK-2900 submitted by alice@company.com"
    },
    {
      "timestamp": "2026-07-05 01:31:06.095256",
      "event": "HUMAN_APPROVAL",
      "severity": "INFO",
      "message": "Human approved resolution. Feedback: yes"
    },
    {
      "timestamp": "2026-07-05 01:31:06.113535",
      "event": "TICKET_CLOSED",
      "severity": "INFO",
      "message": "Ticket TICK-2900 processing ended with status: AUTO_RESOLVED"
    }
  ]
}
```

---

## 🛡️ Security Features

- **PII Scrubbing:** Automatically redacts credit cards, emails, and passwords from incoming description inputs.
- **Prompt Injection Block:** Rejects prompt injection keywords like `ignore guidelines` or `system instruction override` instantly.
- **Domain Verification:** Enforces email domain verification (blocking anything outside `@company.com`, `@corp.com`, or `@internal.net`).

---

## 🔮 Future Improvements

- **Active Directory Sync:** Dynamic user listings synchronization.
- **Cloud Ticket Provider Integration:** Scanners for JIRA and ServiceNow ticketing platforms.
- **Automated Alerts:** Emails on P1 critical alert pager triggers.

---

## 🤝 Contributing

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---

## ✍️ Authors

- **Gururaj Panse** (GitHub: [@gururajpanse](https://github.com/gururajpanse))

---

## 🎙️ Demo Presentation

A complete timed presentation script is available in [**`DEMO_SCRIPT.txt`**](DEMO_SCRIPT.txt).
