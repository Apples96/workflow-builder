# Paradigm + n8n: Complete Analysis and Implementation Guide

**Document:** Complete conversation and analysis about workflow automation options for Paradigm API
**Date:** February 23, 2026
**Context:** Exploring whether to use existing workflow tools (n8n) vs maintaining custom workflow builder

---

## Table of Contents

1. [Initial Question: Can We Use Existing Software?](#1-initial-question)
2. [Analysis of Current Workflow Builder](#2-current-workflow-builder-analysis)
3. [Alternative Solutions Comparison](#3-alternative-solutions)
4. [n8n as Primary Alternative](#4-n8n-deep-dive)
5. [Hybrid Approach Recommendation](#5-hybrid-approach)
6. [On-Premise Implementation for Enterprise](#6-on-premise-implementation)
7. [Enterprise SSO Integration](#7-enterprise-sso-integration)
8. [Data Ownership and Source of Truth](#8-data-ownership)
9. [Deployment Models](#9-deployment-models)
10. [Decision Framework](#10-decision-framework)
11. [Implementation Roadmap](#11-implementation-roadmap)

---

## 1. Initial Question: Can We Use Existing Software?

### The Question

> "Take a close look at the codebase and the way the workflow builder works. Think about whether I could use a pre-existing software (open source or not) where I could simply slot in the Paradigm API instead of re-coding a whole workflow builder."

### Current Workflow Builder Overview

Your system has these key characteristics:

**What it does:**
1. **Natural language input** → User describes workflow in plain English
2. **AI planning** → Claude breaks description into discrete "cells" (steps)
3. **Code generation** → Claude generates Python code for each cell
4. **Execution** → Runs generated code in sandboxed environment
5. **Streaming results** → Real-time output to frontend
6. **Export** → Can generate standalone ZIP packages

**Key capabilities:**
- Cell-based execution with dependency resolution
- Automatic parallelization detection
- LLM-as-judge validation and retry
- Deep Paradigm API integration (all 11 endpoints)
- Standalone package export

### The Core Question

Can this be replaced with existing tools, or is the natural language → code generation truly unique?

---

## 2. Current Workflow Builder Analysis

### Architecture Deep Dive

```
User Input (Natural Language)
    ↓
Workflow Enhancer (Claude)
    ↓
Workflow Planner (Claude)
    ├─ Cell 1: Upload documents
    ├─ Cell 2: Extract buyer info
    ├─ Cell 3: Extract seller info
    └─ Cell 4: Generate report
    ↓
Cell Code Generator (Claude) - generates Python for each cell
    ↓
Cell Executor - runs code in sandbox
    ↓
Results streaming to frontend
```

**Key differentiators:**
1. **Automatic decomposition** - AI figures out the steps
2. **Code generation** - Creates complete Python code
3. **Self-contained exports** - ZIP packages ready to deploy
4. **LLM validation** - Uses Claude to validate outputs

### What Makes It Unique

- Natural language is the ONLY interface (no visual building)
- Full Python code generation (not just API call orchestration)
- Embedded API documentation in generated code
- Cell-based with automatic dependency resolution

---

## 3. Alternative Solutions Comparison

### Option 1: n8n (Open Source Workflow Automation)

**What it is:**
- Visual drag-and-drop workflow builder
- 400+ pre-built integrations
- Self-hostable (open source)
- Enterprise version with SSO/RBAC

**How Paradigm would work:**
- Build 11 custom nodes (one per Paradigm endpoint)
- Users drag nodes and connect them visually
- Configure via forms (not natural language)

**Example workflow in n8n:**
```
[Trigger: Schedule Daily 8am]
    ↓
[Upload File: contracts.pdf]
    ↓
[Paradigm: Document Search]
    (query: "buyer information")
    ↓
[Paradigm: Chat Completion]
    (guided_json: buyer_schema)
    ↓
[Generate Report]
    ↓
[Email Results]
```

**Pros:**
- ✅ Visual workflow building (easier for non-technical users to maintain)
- ✅ Pre-built integrations (Slack, email, databases, etc.)
- ✅ Production-grade (scheduling, monitoring, error handling)
- ✅ Team collaboration (multiple users can edit)
- ✅ Active community and ecosystem

**Cons:**
- ❌ No natural language interface (must build visually)
- ❌ No automatic workflow decomposition
- ❌ Need to build 11 custom Paradigm nodes (2-4 weeks)
- ❌ No standalone package export

**Verdict:** Good for production workflows, loses the "magic" of natural language.

---

### Option 2: Zapier / Make (Integromat)

**What it is:**
- Commercial SaaS workflow automation
- Cloud-based, no self-hosting
- Many pre-built integrations

**Paradigm integration:**
- Would need custom Paradigm integration (similar to n8n)
- Less flexible than n8n
- Expensive at scale

**Verdict:** Not recommended - expensive, cloud-locked, less control.

---

### Option 3: LangChain + Streamlit

**What it is:**
- LangChain: Python framework for LLM applications
- Streamlit: Simple Python UI framework

**How it would work:**
- Rebuild workflow logic using LangChain
- Use LangChain agents to call Paradigm API
- Build simple UI with Streamlit
- Port existing prompts to LangChain format

**Pros:**
- ✅ Modern, popular framework
- ✅ Good for LLM-based document processing
- ✅ Full Python control

**Cons:**
- ❌ 3-4 weeks to rebuild to reach parity
- ❌ Would lose production-ready FastAPI backend
- ❌ Need to rebuild UI, export features, validation

**Verdict:** Only if you want to modernize using a popular framework.

---

### Option 4: Apache Airflow / Prefect / Temporal

**What it is:**
- General workflow orchestration tools
- Require manual Python coding

**Verdict:** Not suitable - no natural language capabilities, require coding.

---

### Option 5: Retool Workflows

**What it is:**
- Enterprise low-code platform
- Good UI builder

**Verdict:** Expensive, cloud-locked, no natural language generation.

---

## 4. n8n Deep Dive

### Why n8n is the Best Alternative

1. **Open source** - No licensing restrictions
2. **Self-hostable** - Customer control
3. **Visual workflow building** - Production-grade alternative to natural language
4. **Extensible** - Can build custom Paradigm nodes
5. **Enterprise features** - SSO, RBAC, audit logs (in paid version)
6. **Active ecosystem** - 400+ integrations, growing community

### What You'd Need to Build

#### Custom Paradigm Nodes (11 total)

**Node 1: Paradigm Document Search**
```typescript
export class ParadigmDocumentSearch implements INodeType {
  description = {
    displayName: 'Paradigm Document Search',
    name: 'paradigmDocumentSearch',
    inputs: ['main'],
    outputs: ['main'],
    credentials: [{name: 'paradigmApi', required: true}],
    properties: [
      {
        displayName: 'Search Query',
        name: 'query',
        type: 'string',
        required: true
      },
      {
        displayName: 'File IDs',
        name: 'fileIds',
        type: 'string',
        default: ''
      },
      {
        displayName: 'Max Results',
        name: 'maxResults',
        type: 'number',
        default: 5
      }
    ]
  }

  async execute(this: IExecuteFunctions) {
    const credentials = await this.getCredentials('paradigmApi');
    const query = this.getNodeParameter('query', 0) as string;
    const fileIds = this.getNodeParameter('fileIds', 0) as string;

    const response = await this.helpers.request({
      method: 'POST',
      url: `${credentials.baseUrl}/api/v2/chat/completions`,
      headers: {
        'Authorization': `Bearer ${credentials.apiKey}`
      },
      body: {
        query,
        file_ids: fileIds.split(',').map(id => parseInt(id.trim()))
      }
    });

    return [this.helpers.returnJsonArray(response.results)];
  }
}
```

**Other nodes needed:**
- Node 2: Paradigm Analyze Documents
- Node 3: Paradigm Chat Completion (with guided output)
- Node 4: Paradigm Upload File
- Node 5: Paradigm Get File
- Node 6: Paradigm Delete File
- Node 7: Paradigm Wait for Embedding
- Node 8: Paradigm Get File Chunks
- Node 9: Paradigm Filter Chunks
- Node 10: Paradigm Query
- Node 11: Paradigm Analyze Image

**Development effort:** 2-4 weeks for experienced TypeScript developer

---

## 5. Hybrid Approach Recommendation

### The Best Strategy: Use BOTH

Instead of replacing your workflow builder entirely, use both tools for different purposes:

```
┌─────────────────────────────────────────┐
│         Paradigm Ecosystem              │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Current Workflow Builder        │  │
│  │  • Natural language interface    │  │
│  │  • Rapid prototyping             │  │
│  │  • R&D / experimentation         │  │
│  │  • One-off complex workflows     │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  n8n (NEW)                       │  │
│  │  • Visual workflow building      │  │
│  │  • Production workflows          │  │
│  │  • Scheduled/recurring jobs      │  │
│  │  • Team collaboration            │  │
│  │  • Monitoring & alerts           │  │
│  └──────────────────────────────────┘  │
│                                         │
│  Both use same Paradigm API nodes      │
└─────────────────────────────────────────┘
```

### When to Use Each

**Use Current Workflow Builder for:**
- ✅ Quick prototyping ("Let me test this idea")
- ✅ One-off analysis tasks
- ✅ R&D and experimentation
- ✅ When natural language is faster than visual building
- ✅ Complex logic that's easier to describe than build

**Use n8n for:**
- ✅ Production recurring workflows
- ✅ Scheduled jobs (daily reports, weekly analysis)
- ✅ Workflows that need monitoring and alerts
- ✅ Team-maintained workflows (multiple people editing)
- ✅ Integration with other systems (email, Slack, databases)

### Migration Path

```
User starts with natural language builder:
  "Analyze contracts, extract buyer/seller, email report"
    ↓
Workflow Builder generates and runs code
    ↓
User validates: "Yes, this is what I need"
    ↓
Rebuild in n8n for production:
  - Visual workflow with same logic
  - Add scheduling (daily at 8am)
  - Add error alerts (email on failure)
  - Add monitoring
    ↓
Production workflow runs reliably in n8n
```

### Benefits of Hybrid Approach

1. **Best of both worlds**
   - Natural language for experimentation
   - Visual workflows for production

2. **Gradual adoption**
   - Keep current builder working
   - Add n8n incrementally
   - No "big bang" migration

3. **Different user personas**
   - Developers/analysts: Use natural language builder
   - Operations/IT: Use n8n for production

4. **Shared investment**
   - Build Paradigm nodes once
   - Use in both systems
   - No duplicate work

---

## 6. On-Premise Implementation for Enterprise

### What It Entails for On-Premise Customer

When an enterprise customer wants to deploy n8n on-premise for Paradigm workflows:

#### Week 1: Infrastructure Setup

**Hardware requirements:**
```
Minimum (small deployment):
  • CPU: 4 cores
  • RAM: 8 GB
  • Storage: 50 GB SSD
  • OS: Ubuntu 22.04 LTS / RHEL 8+

Recommended (production):
  • CPU: 8 cores
  • RAM: 16 GB
  • Storage: 200 GB SSD
  • Database: PostgreSQL 14+
```

**Network requirements:**
- Outbound HTTPS to Paradigm API (paradigm.lighton.ai)
- Internal network access for users (port 5678)
- Optional: Reverse proxy (nginx) for HTTPS/SSL

**Docker Compose deployment:**
```yaml
version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=n8n
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - LIGHTON_API_KEY=${LIGHTON_API_KEY}
    volumes:
      - n8n_data:/home/node/.n8n
      - ./n8n-nodes-paradigm:/home/node/.n8n/custom
    depends_on:
      - postgres

  postgres:
    image: postgres:14
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  n8n_data:
  postgres_data:
```

**Deployment time:** 1-2 hours

---

#### Week 2-6: Custom Node Development

**Build 11 Paradigm nodes** (one per API endpoint)

**Example: Document Search Node**
```typescript
// paradigm-document-search.node.ts
import { IExecuteFunctions, INodeType, INodeTypeDescription } from 'n8n-workflow';

export class ParadigmDocumentSearch implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'Paradigm Document Search',
    name: 'paradigmDocumentSearch',
    group: ['transform'],
    version: 1,
    description: 'Search documents using Paradigm API',
    defaults: {
      name: 'Paradigm Document Search',
    },
    inputs: ['main'],
    outputs: ['main'],
    credentials: [
      {
        name: 'paradigmApi',
        required: true,
      },
    ],
    properties: [
      {
        displayName: 'Query',
        name: 'query',
        type: 'string',
        default: '',
        required: true,
        description: 'Search query',
      },
      {
        displayName: 'File IDs',
        name: 'fileIds',
        type: 'string',
        default: '',
        description: 'Comma-separated file IDs',
      },
    ],
  };

  async execute(this: IExecuteFunctions) {
    const items = this.getInputData();
    const credentials = await this.getCredentials('paradigmApi');

    const results = [];

    for (let i = 0; i < items.length; i++) {
      const query = this.getNodeParameter('query', i) as string;
      const fileIds = this.getNodeParameter('fileIds', i) as string;

      const response = await this.helpers.request({
        method: 'POST',
        url: `${credentials.baseUrl}/api/v2/chat/completions`,
        headers: {
          'Authorization': `Bearer ${credentials.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: {
          query,
          file_ids: fileIds.split(',').map(id => parseInt(id.trim())),
        },
        json: true,
      });

      results.push({ json: response });
    }

    return [results];
  }
}
```

**Development effort:** 2-4 weeks (77-154 hours total)

---

#### Week 7-8: User Training

**Session 1: n8n Basics (2 hours)**
- Interface overview
- Creating workflows
- Triggers, nodes, connections
- Testing and debugging

**Session 2: Paradigm Nodes (2 hours)**
- Overview of 11 Paradigm nodes
- File upload and management
- Document search and analysis
- Structured data extraction (guided_json, guided_regex)

**Session 3: Production Workflows (2 hours)**
- Error handling strategies
- Retry logic
- Scheduling workflows
- Monitoring and alerts
- Team collaboration

---

#### Week 9-12: Migration and Go-Live

**Migration process:**
1. Identify top 5-10 workflows from current builder
2. Rebuild visually in n8n
3. Side-by-side testing (old vs new)
4. Documentation for each workflow
5. Gradual cutover to n8n

**Example migration:**

**Before (Natural Language):**
> "Every morning, analyze contracts uploaded yesterday, extract key terms, flag non-standard clauses, email report to legal team"

**After (Visual n8n Workflow):**
```
[Trigger: Cron - Daily 8am]
    ↓
[Get Yesterday's Files]
    ↓
[Loop: For Each File]
    ↓
[Paradigm: Wait for Embedding]
    ↓
[Paradigm: Chat Completion]
    (guided_json: contract_schema)
    ↓
[Check Non-Standard Clauses]
    (IF node: check patterns)
    ↓
[Aggregate Results]
    ↓
[Generate HTML Report]
    ↓
[Email Legal Team]
```

**Total implementation time:** 12 weeks (3 months)

---

### Cost Analysis

#### One-Time Costs

| Item | Internal Cost | External Consultant Cost |
|------|---------------|--------------------------|
| Infrastructure setup | 1 day IT | €800 |
| n8n deployment | 1 day DevOps | €1,200 |
| Custom node development | 2-4 weeks Dev | €8,000-€16,000 |
| Training materials | 1 week Dev | €2,000 |
| User training | 3 sessions | €1,500 |
| **TOTAL** | **5-7 weeks internal** | **€13,500-€21,500** |

#### Ongoing Costs

| Item | Annual Cost |
|------|------------|
| Server hosting (on-prem) | €0 (existing infrastructure) |
| n8n license | €0 (self-hosted open source) |
| Maintenance (updates) | 1 day/month = €6,000/year |
| **TOTAL** | **€6,000/year** |

---

## 7. Enterprise SSO Integration

### The Enterprise Question

> "How would n8n pair up with Paradigm for an enterprise customer? LightOn can't commercialize n8n, but we want n8n to sync with Paradigm SSO and accounts, so employees pass their API key into n8n workflows."

### Business Model (No License Conflict)

**What LightOn provides (Free/Open Source):**
- ✅ 11 custom Paradigm nodes for n8n (Apache 2.0 license)
- ✅ Integration documentation
- ✅ Professional services (setup, training)

**What customer purchases separately:**
- From **n8n.io**: n8n Enterprise license (~$50-100/user/month)
- From **LightOn**: Paradigm Enterprise with SSO

**No conflict:** LightOn doesn't resell n8n, just provides integration layer.

---

### SSO Architecture: Paradigm as Identity Provider

```
┌────────────────────────────────────────────┐
│         Paradigm (Master System)           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Users (employees)                       │
│  • Groups/Teams                            │
│  • API Keys (one per user)                 │
│  • SSO/SAML Identity Provider              │
│  • Document permissions                    │
└──────────────────┬─────────────────────────┘
                   │
                   │ SAML Assertion (at login)
                   │ Contains: email, teams, API key
                   ↓
┌────────────────────────────────────────────┐
│           n8n (Replica System)             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Users (mirrored from Paradigm)          │
│  • Teams (mirrored from Paradigm)          │
│  • Credentials (API keys from Paradigm)    │
│  • Workflows (owned by n8n)                │
└────────────────────────────────────────────┘
```

### How SSO Works

**Step 1: User logs into n8n**
```
User visits: https://workflows.company.com
  ↓
n8n redirects to: https://paradigm.company.com/saml/sso
```

**Step 2: Paradigm authenticates and creates SAML assertion**
```xml
<saml:Assertion>
  <saml:Subject>alice@company.com</saml:Subject>
  <saml:Attributes>
    <Attribute Name="email">
      <AttributeValue>alice@company.com</AttributeValue>
    </Attribute>
    <Attribute Name="firstName">
      <AttributeValue>Alice</AttributeValue>
    </Attribute>
    <Attribute Name="groups">
      <AttributeValue>Legal</AttributeValue>
      <AttributeValue>Contract Analysis</AttributeValue>
    </Attribute>
    <Attribute Name="paradigm_api_key">
      <AttributeValue>lgn_sk_abc123...</AttributeValue>
    </Attribute>
  </saml:Attributes>
</saml:Assertion>
```

**Step 3: n8n receives assertion and auto-creates user**
```javascript
// n8n processes SAML assertion
{
  email: "alice@company.com",
  name: "Alice Johnson",
  teams: ["Legal", "Contract Analysis"],
  credentials: {
    name: "Paradigm API (Personal)",
    type: "paradigmApi",
    data: {
      apiKey: "lgn_sk_abc123...",  // From SAML
      baseUrl: "https://paradigm.lighton.ai"
    }
  }
}
```

**Step 4: User lands in n8n with everything configured**
- ✅ Account auto-created
- ✅ Teams synced
- ✅ Personal API key stored
- ✅ Ready to build workflows

### Per-User API Keys Enable

**1. Proper audit trails:**
```json
{
  "timestamp": "2026-02-23T14:30:00Z",
  "api_endpoint": "/api/v2/chat/completions",
  "user": "alice@company.com",  // Clear attribution
  "workflow_id": "contract-analysis",
  "file_ids": [12345],
  "query": "Extract buyer information"
}
```

**2. Individual quotas:**
```javascript
{
  "user": "alice@company.com",
  "team": "Legal",
  "quotas": {
    "document_searches_per_day": 1000,
    "documents_analyzed_per_month": 5000
  },
  "current_usage": {
    "searches_today": 234,
    "analyzed_this_month": 1892
  }
}
```

**3. Security:**
- Alice leaves company → Revoke her API key → Her workflows stop
- No shared credentials = no "service account" risks
- Compliance (GDPR, SOC2) requires knowing who accessed what

---

## 8. Data Ownership and Source of Truth

### The Critical Question

> "What is shared between Paradigm and n8n? Where is it piloted from? Who manages groups, permissions, SSO?"

### The Golden Rule

```
╔════════════════════════════════════════════════╗
║  PARADIGM MANAGES PEOPLE                       ║
║  N8N MANAGES WORKFLOWS                         ║
║                                                ║
║  Data flows: Paradigm → n8n (ONE WAY)         ║
╚════════════════════════════════════════════════╝
```

### Data Ownership Matrix

| What | Owned By | Managed In | Flows To | Sync Method |
|------|----------|------------|----------|-------------|
| **Users** | Paradigm | Paradigm Admin | → n8n | SAML (at login) |
| **Teams/Groups** | Paradigm | Paradigm Admin | → n8n | SAML claims |
| **User Roles** | Paradigm | Paradigm Admin | → n8n | SAML claims |
| **API Keys** | Paradigm | Paradigm (auto-gen) | → n8n | SAML claims |
| **SSO/Auth** | Paradigm | Paradigm Admin | → n8n validates | SAML 2.0 |
| **Document Permissions** | Paradigm | Paradigm/Doc Owner | (stays in Paradigm) | - |
| **Workflows** | n8n | n8n Users | (stays in n8n) | - |
| **Workflow Permissions** | n8n | n8n Workflow Owner | Uses Paradigm teams | - |

### Where Admins Make Changes

#### Paradigm Admin Console

**User Management:**
```
Action: Add new employee
Location: Paradigm Admin Console

Steps:
1. Create user: alice@company.com
2. Assign team: Legal
3. Set role: Document Analyst
4. Paradigm auto-generates API key

Result:
✅ User can log into Paradigm
✅ Next time user logs into n8n → auto-created via SAML
✅ Teams synced
✅ API key stored
```

**Team Management:**
```
Action: Create new team
Location: Paradigm Admin Console

Steps:
1. Create team: "Contract Analysis"
2. Add members: alice, bob

Result:
✅ Team exists in Paradigm
✅ Next SAML login → n8n creates team
✅ Workflows can be shared with team
✅ Document permissions reference team
```

**User Lifecycle:**
```
Employee joins:
  ✓ Create in Paradigm
  ✗ Don't create in n8n (auto-synced)

Employee changes teams:
  ✓ Update in Paradigm
  ✗ Don't update in n8n (auto-synced)

Employee leaves:
  ✓ Disable in Paradigm
  ✓ API key revoked immediately
  ✗ n8n login fails (SSO blocked)
```

#### n8n Admin Console

**Workflow Management (n8n-only):**
```
Actions n8n admin CAN do:
✓ Create/edit workflows
✓ Set workflow permissions:
  - Viewers: "Legal" team (from Paradigm)
  - Editors: "Contract Analysis" team (from Paradigm)
✓ Schedule workflows
✓ View execution logs

Actions n8n admin CANNOT do:
✗ Create users (must come from Paradigm)
✗ Create Paradigm teams
✗ Modify user's API key
✗ Change SSO settings
```

### Synchronization Methods

**Option 1: SAML Only (Just-in-Time)**
- User data synced ONLY when user logs in
- Simple setup, no background sync
- Changes don't apply until next login

**Option 2: SAML + SCIM (Real-Time)**
- SCIM = System for Cross-domain Identity Management
- Paradigm detects change → Sends SCIM API call → n8n updates immediately
- Example: Admin adds Alice to Finance team → n8n updated in seconds
- More complex, requires SCIM server in Paradigm

### Example User Journey

**Day 1 - Alice Joins Company:**
```
1. HR creates Alice in Paradigm:
   - Email: alice@company.com
   - Team: Legal
   - Role: Document Analyst
   - Paradigm generates API key

2. Alice logs into n8n (first time):
   - Clicks "Login with Paradigm SSO"
   - Redirected to Paradigm
   - Authenticates
   - Redirected back to n8n
   - n8n auto-creates account with teams and API key

3. Alice starts building workflows immediately
```

**Week 2 - Alice Promoted:**
```
1. Manager updates in Paradigm:
   - Adds to team: "Contract Analysis"
   - Changes role: Senior Document Analyst

2. Next time Alice logs into n8n:
   - SAML includes new team
   - Can now access "Contract Analysis" workflows
   - New permissions applied
```

**Month 3 - Alice Switches Departments:**
```
1. HR updates in Paradigm:
   - Remove from: Legal
   - Add to: Finance

2. Next time Alice logs into n8n:
   - Teams updated: Finance
   - Loses access to Legal workflows
   - Gains access to Finance workflows
```

---

## 9. Deployment Models

### The Multi-Tenancy Question

> "If LightOn hosts n8n, can one instance serve multiple customers? Or does LightOn need a new instance for each customer?"

### Three Deployment Models

#### Model A: Shared Multi-Tenant (Like Zapier)

```
┌────────────────────────────────────────┐
│    One n8n Instance for ALL customers  │
│                                        │
│  Customer A (Acme Corp team)           │
│  Customer B (Widget Inc team)          │
│  Customer C (Example LLC team)         │
│                                        │
│  • Shared database (team isolation)    │
│  • Shared workers                      │
│  • Shared infrastructure               │
└────────────────────────────────────────┘
```

**Cost per customer:** $50-100/month
**Pros:** Cheapest, instant onboarding
**Cons:** Noisy neighbor risk, security concerns
**Use for:** Trials, freemium, SMB customers

---

#### Model B: Dedicated Instance Per Customer (Like Heroku)

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Customer A      │  │  Customer B      │  │  Customer C      │
│  • Own n8n       │  │  • Own n8n       │  │  • Own n8n       │
│  • Own database  │  │  • Own database  │  │  • Own database  │
│  • Own URL       │  │  • Own URL       │  │  • Own URL       │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

**Cost per customer:** $480/month
**Charge customer:** $2,000/month
**Profit margin:** 76%

**Pros:** Complete isolation, meets strict compliance
**Cons:** Expensive infrastructure, operational overhead
**Use for:** Enterprise (>1000 employees), regulated industries

---

#### Model C: Hybrid - Namespace Isolation (RECOMMENDED)

```
┌────────────────────────────────────────────────┐
│    Shared Kubernetes Cluster                   │
│                                                │
│  ┌──────────────────────────────────────┐     │
│  │  Namespace: customer-acme            │     │
│  │  • n8n pods                          │     │
│  │  • Isolated database                 │     │
│  │  • Network policies                  │     │
│  └──────────────────────────────────────┘     │
│                                                │
│  ┌──────────────────────────────────────┐     │
│  │  Namespace: customer-widget          │     │
│  │  • n8n pods                          │     │
│  │  • Isolated database                 │     │
│  │  • Network policies                  │     │
│  └──────────────────────────────────────┘     │
│                                                │
│  Shared: K8s control plane, monitoring        │
└────────────────────────────────────────────────┘
```

**Cost breakdown:**
```
Shared costs (÷ 10 customers):     $80/month per customer
Per-customer resources:            $210/month
───────────────────────────────────────────────
Total cost per customer:           $290/month
Charge customer:                   $500/month
Profit margin:                     42%
```

**Pros:** Good isolation, cost-efficient, scalable
**Cons:** Moderate complexity
**Use for:** Most customers (SMB + mid-market) - **THE SWEET SPOT**

---

### Comparison Matrix

| Factor | Shared (A) | Dedicated (B) | Hybrid (C) |
|--------|------------|---------------|------------|
| **Cost per customer** | $50-100/mo | $480/mo | $290/mo |
| **Charge customer** | $200/mo | $2,000/mo | $500/mo |
| **Isolation** | Low | High | Medium |
| **Onboarding** | 1 minute | 30 minutes | 5 minutes |
| **Compliance** | Basic | Full (HIPAA) | Most (SOC2) |
| **Noisy neighbor** | High risk | None | Low risk |
| **Best for** | Trials/SMB | Enterprise | Most customers |

---

### Customer-Owned n8n Integration

When customer already has n8n:

**Option 1: Dual SSO (Recommended)**
```
Customer's n8n login:
┌──────────────────────────────┐
│  [Login with Azure AD]       │ ← Existing users
│  [Login with Paradigm]       │ ← NEW: Paradigm users
└──────────────────────────────┘
```

- Add Paradigm as 2nd SAML IdP
- Paradigm users get API keys automatically
- Existing setup unchanged

**Option 2: Separate Instance**
- Deploy new n8n just for Paradigm workflows
- Complete isolation from existing n8n
- Two different URLs

**Option 3: Manual Credentials**
- Just install Paradigm nodes
- Users manually copy/paste API keys
- No SSO integration
- Simplest but least automated

---

## 10. Decision Framework

### For Customer: Which Deployment Model?

```
Do you already have n8n?
├─ Yes → Keep it, add Paradigm nodes
│  ├─ Have n8n Enterprise? → Dual SSO
│  ├─ Don't have Enterprise? → Manual credentials
│  └─ Want isolation? → Separate instance
│
└─ No → LightOn hosts n8n
   ├─ Trial/POC → Free trial (Model A)
   ├─ SMB (<100 users) → Standard tier $500/mo (Model C)
   ├─ Mid-market (100-1000) → Standard tier $500/mo (Model C)
   └─ Enterprise (>1000) OR regulated → Enterprise tier $2,000/mo (Model B)
```

### For LightOn: Recommended Product Tiers

```
┌─────────────────────────────────────────────────┐
│  Trial/POC                                      │
│  • Free for 30 days                             │
│  • Shared multi-tenant (Model A)                │
│  • Limited to 10 workflows                      │
└─────────────────────────────────────────────────┘
              ↓ Convert to
┌─────────────────────────────────────────────────┐
│  Standard Tier (MOST CUSTOMERS)                 │
│  • $500/month                                   │
│  • Kubernetes namespace isolation (Model C)     │
│  • For: SMB, mid-market (20-500 employees)      │
│  • Cost: $290 → Margin: 42%                     │
└─────────────────────────────────────────────────┘
              ↓ Upgrade to
┌─────────────────────────────────────────────────┐
│  Enterprise Tier                                │
│  • $2,000/month                                 │
│  • Dedicated instance (Model B)                 │
│  • For: Large enterprise, regulated industries  │
│  • Cost: $480 → Margin: 76%                     │
└─────────────────────────────────────────────────┘
```

### When to Use What

**Current Workflow Builder:**
- ✅ One-off, experimental workflows
- ✅ Rapid prototyping
- ✅ "Let me test this idea quickly"
- ✅ Complex logic easier to describe than build
- ✅ R&D and innovation

**n8n:**
- ✅ Production recurring workflows
- ✅ Scheduled execution required
- ✅ Team collaboration needed
- ✅ Monitoring and alerts important
- ✅ Integration with other systems (email, Slack, etc.)
- ✅ Workflow versioning and audit trail

---

## 11. Implementation Roadmap

### Phase 1: Foundation (Month 1-2)

**For LightOn:**
- [ ] Develop 11 Paradigm n8n nodes
- [ ] Publish to npm and n8n marketplace (open source)
- [ ] Create integration documentation
- [ ] Build reference Docker deployment
- [ ] Set up demo environment

**Deliverables:**
- `n8n-nodes-paradigm` package on npm
- Integration guide (PDF + video)
- Docker Compose templates
- Demo workflows (5 examples)

---

### Phase 2: Paradigm SSO Integration (Month 2-3)

**Technical work:**
- [ ] Implement SAML IdP in Paradigm Enterprise
- [ ] Add API key claims to SAML assertions
- [ ] Test with n8n Enterprise
- [ ] Document user provisioning flow
- [ ] Create troubleshooting guide

**Testing:**
- [ ] SSO login flow (10+ test users)
- [ ] API key sync (rotation, revocation)
- [ ] Team membership sync
- [ ] Error scenarios (expired certs, etc.)

---

### Phase 3: Pilot Customers (Month 3-6)

**Select 2-3 pilot customers:**

**Customer Type A: Existing Paradigm customer (on-premise)**
- Deploy n8n on their infrastructure
- Dual SSO integration
- Migrate 3-5 workflows
- 30-day evaluation

**Customer Type B: New Paradigm + n8n customer**
- LightOn-hosted (Hybrid Model C)
- SSO integration
- Build workflows from scratch
- 60-day evaluation

**Success criteria:**
- ✅ Users can log in via Paradigm SSO
- ✅ API keys sync automatically
- ✅ 5+ production workflows running
- ✅ Customer satisfaction >8/10
- ✅ Technical issues <5 per month

---

### Phase 4: Production Rollout (Month 6-9)

**Sales enablement:**
- [ ] Create sales playbook ("When to recommend n8n")
- [ ] Pricing calculator (cost model per customer size)
- [ ] ROI calculator (n8n vs custom development)
- [ ] Demo videos (5-10 minutes each)
- [ ] Customer case studies (2-3 written)

**Operations:**
- [ ] Set up Kubernetes cluster (for hosted customers)
- [ ] Implement customer provisioning automation
- [ ] Build monitoring dashboards
- [ ] Create runbooks (incident response, scaling)
- [ ] Train support team (2-day workshop)

**Marketing:**
- [ ] Blog post: "Paradigm now integrates with n8n"
- [ ] Webinar: "Building production workflows with Paradigm"
- [ ] Update product pages
- [ ] Email campaign to existing customers

---

### Phase 5: Continuous Improvement (Month 9+)

**Product enhancements:**
- [ ] Add more Paradigm nodes (based on feedback)
- [ ] Improve error messages
- [ ] Build workflow templates library (10+ templates)
- [ ] Create self-service customer portal
- [ ] Implement usage analytics

**Expansion:**
- [ ] Target 20 customers by end of Month 12
- [ ] 50% adoption rate among Paradigm Enterprise customers
- [ ] $10,000 MRR from n8n services
- [ ] <5% churn rate

---

## Summary and Recommendations

### Key Decisions

1. **Don't replace the workflow builder entirely**
   - Keep it for rapid prototyping and R&D
   - Add n8n for production workflows
   - Hybrid approach is best

2. **Build Paradigm nodes for n8n**
   - 11 custom nodes (2-4 weeks development)
   - Open source (Apache 2.0 license)
   - Publish to npm and n8n marketplace

3. **LightOn doesn't commercialize n8n**
   - Customers buy n8n Enterprise directly from n8n.io
   - LightOn provides: nodes, integration, professional services
   - No licensing conflict

4. **Paradigm is master for identity/access**
   - Paradigm manages: users, teams, API keys, SSO
   - n8n manages: workflows, executions
   - Data flows: Paradigm → n8n (one way)

5. **Use Hybrid hosting model (Model C)**
   - Kubernetes namespace per customer
   - Shared infrastructure, isolated databases
   - Cost: $290/month, charge $500/month
   - Add Dedicated tier ($2,000/month) for enterprise

### Implementation Timeline

| Phase | Duration | Key Milestone |
|-------|----------|---------------|
| Foundation | 2 months | Paradigm nodes published |
| SSO Integration | 1 month | SAML working with test customers |
| Pilot | 3 months | 2-3 customers in production |
| Rollout | 3 months | Sales-ready, 10+ customers |
| Scale | Ongoing | 20+ customers, $10k MRR |

**Total to production-ready:** 6 months

### Success Metrics

**By Month 6:**
- [ ] 10 customers using n8n with Paradigm
- [ ] 50+ production workflows
- [ ] 95% uptime
- [ ] <5 support tickets per customer per month
- [ ] 8/10 customer satisfaction

**By Month 12:**
- [ ] 20 customers
- [ ] $10,000 MRR from n8n services
- [ ] 200+ workflows in production
- [ ] Self-service onboarding (<1 hour)

### Total Investment

**Development (one-time):**
- Paradigm nodes: 2-4 weeks (€8,000-€16,000)
- SSO integration: 2-3 weeks (€4,000-€6,000)
- Documentation: 1 week (€2,000)
- Infrastructure setup: 1 week (€2,000)
- **Total: €16,000-€26,000**

**Ongoing (monthly):**
- Infrastructure (10 customers): €2,900/month
- Support/maintenance: €2,000/month
- **Total: €4,900/month**

**Revenue (monthly, 10 customers):**
- Standard tier (8 customers × €500): €4,000/month
- Enterprise tier (2 customers × €2,000): €4,000/month
- **Total: €8,000/month**

**Break-even:** Month 3-4 (after 8-10 paying customers)

---

## Conclusion

The hybrid approach of keeping your current workflow builder while adding n8n gives you:

✅ **Best of both worlds:** Natural language for prototyping, visual workflows for production
✅ **Gradual adoption:** No risky "big bang" migration
✅ **Market differentiation:** "Paradigm works with n8n" attracts customers
✅ **Revenue opportunity:** €8,000/month from 10 customers
✅ **No vendor conflict:** LightOn provides integration, not n8n itself

**Bottom line:** This is a strategic move that makes Paradigm easier to adopt while opening a new services revenue stream.

---

**Document prepared:** February 23, 2026
**For:** LightOn - Paradigm API workflow automation strategy
**Contact:** [Your contact information]
