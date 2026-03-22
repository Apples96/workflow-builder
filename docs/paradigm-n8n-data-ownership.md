# Paradigm + n8n: Data Ownership and Source of Truth

## Executive Summary

In the Paradigm + n8n enterprise integration, **Paradigm is the master system** for all organizational data (users, groups, permissions, SSO). n8n receives this data and uses it for workflow execution, but doesn't own it.

**Simple rule:** Paradigm manages people and access. n8n manages workflows.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    PARADIGM (MASTER)                         │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Users (employees)                                         │
│  • Groups/Teams                                              │
│  • Permissions (who can access what documents)               │
│  • SSO/SAML Identity Provider                                │
│  • API Keys (one per user)                                   │
│  • Document access control                                   │
│  • Usage quotas                                              │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      │ SAML Assertion (SSO)
                      │ SCIM Protocol (User Sync)
                      │ API Calls (Quota Checks)
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│                     N8N (REPLICA)                            │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Users (mirrored from Paradigm via SAML/SCIM)              │
│  • Teams (mirrored from Paradigm)                            │
│  • Credentials (API keys received from Paradigm)             │
│  • Workflows (owned by n8n)                                  │
│  • Workflow permissions (who can edit which workflow)        │
│  • Execution history                                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 1. Data Ownership Matrix

| Data Type | Master System | Replica System | Sync Method | Update Direction |
|-----------|---------------|----------------|-------------|------------------|
| **Users** | Paradigm | n8n | SAML (JIT) or SCIM | Paradigm → n8n |
| **Groups/Teams** | Paradigm | n8n | SAML claims or SCIM | Paradigm → n8n |
| **User Roles** | Paradigm | n8n | SAML claims | Paradigm → n8n |
| **API Keys** | Paradigm | n8n | SAML claims (at login) | Paradigm → n8n |
| **SSO/Authentication** | Paradigm (IdP) | n8n (SP) | SAML 2.0 | Paradigm validates |
| **Document Permissions** | Paradigm | - | - | Paradigm only |
| **Usage Quotas** | Paradigm | - | API responses | Paradigm enforces |
| **Workflows** | - | n8n | - | n8n only |
| **Workflow Permissions** | Hybrid | n8n | Teams from Paradigm | Both systems |
| **Execution Logs** | n8n | Paradigm (optional) | API callbacks | n8n → Paradigm |

---

## 2. User Lifecycle: Where Things Happen

### Scenario 1: New Employee Joins Company

**Step 1: Admin creates user in Paradigm**
```
Location: Paradigm Admin Console
Action: HR/IT admin creates user

Input:
  - Email: alice@company.com
  - Name: Alice Johnson
  - Department: Legal
  - Team: Contract Analysis
  - Role: Document Analyst

Paradigm auto-generates:
  - User ID: user_123
  - API Key: lgn_sk_abc123...
  - Team membership: team_legal_456
```

**Step 2: User logs into n8n for first time**
```
Location: n8n login screen
Action: Alice clicks "Login with Paradigm SSO"

Flow:
  1. Redirect to Paradigm SSO
  2. Alice authenticates (or already logged in)
  3. Paradigm sends SAML assertion to n8n:

     <saml:Assertion>
       <saml:Subject>alice@company.com</saml:Subject>
       <saml:Attributes>
         <Attribute Name="email">alice@company.com</Attribute>
         <Attribute Name="firstName">Alice</Attribute>
         <Attribute Name="lastName">Johnson</Attribute>
         <Attribute Name="groups">Legal, Contract Analysis</Attribute>
         <Attribute Name="paradigm_role">document_analyst</Attribute>
         <Attribute Name="paradigm_api_key">lgn_sk_abc123...</Attribute>
       </saml:Attributes>
     </saml:Assertion>

  4. n8n receives assertion and auto-creates user:
     - Email: alice@company.com
     - Teams: Legal, Contract Analysis
     - Role: Mapped from paradigm_role → n8n role
     - Credential: Stores API key in vault

  5. Alice lands in n8n dashboard
```

**Result:**
- ✅ User exists in BOTH systems
- ✅ Paradigm is source of truth
- ✅ n8n auto-synced via SAML

---

### Scenario 2: User Changes Teams

**Location: Paradigm Admin Console**
```
Admin changes:
  Alice: Legal → Finance

Next time Alice logs into n8n:
  1. SAML assertion includes: groups="Finance"
  2. n8n updates Alice's team memberships
  3. Alice can now access Finance workflows
  4. Alice can no longer access Legal workflows (unless shared)
```

**No action needed in n8n** - automatically synced at next login.

---

### Scenario 3: User Leaves Company

**Step 1: Paradigm admin disables user**
```
Location: Paradigm Admin Console
Action: Disable alice@company.com

Paradigm:
  - User status: Active → Disabled
  - API key: Revoked immediately
  - SSO: Login attempts fail
```

**Step 2: Automatic impact on n8n**
```
Immediate:
  - Alice cannot log into n8n (SSO fails)
  - Any running workflows with her API key fail

Within 24 hours:
  - n8n SCIM sync (optional) marks user as inactive
  - Or: Manual n8n admin action to disable/delete

Workflow handling:
  - Alice's personal workflows: Archived or reassigned
  - Shared workflows: Other users can still use them
```

---

## 3. Groups/Teams: Paradigm → n8n

### How Teams Flow from Paradigm

**In Paradigm:**
```json
// Paradigm organizational structure
{
  "organization": "Acme Corp",
  "teams": [
    {
      "id": "team_legal_456",
      "name": "Legal",
      "members": ["alice@company.com", "bob@company.com"],
      "parent_team": null
    },
    {
      "id": "team_contracts_789",
      "name": "Contract Analysis",
      "members": ["alice@company.com"],
      "parent_team": "team_legal_456"
    },
    {
      "id": "team_finance_012",
      "name": "Finance",
      "members": ["charlie@company.com"],
      "parent_team": null
    }
  ]
}
```

**Via SAML to n8n:**
```xml
<!-- SAML assertion for Alice -->
<saml:Attribute Name="groups">
  <saml:AttributeValue>Legal</saml:AttributeValue>
  <saml:AttributeValue>Contract Analysis</saml:AttributeValue>
</saml:Attribute>
```

**In n8n (auto-created from SAML):**
```javascript
// n8n team structure (mirrored)
{
  "teams": [
    {
      "name": "Legal",
      "source": "paradigm",  // Indicates this came from Paradigm
      "external_id": "team_legal_456",
      "members": ["alice@company.com", "bob@company.com"]
    },
    {
      "name": "Contract Analysis",
      "source": "paradigm",
      "external_id": "team_contracts_789",
      "members": ["alice@company.com"]
    }
  ]
}
```

**Important:** n8n can also have **local teams** (created directly in n8n for workflow organization), but Paradigm teams take precedence for access control.

---

## 4. Permissions: Hybrid Model

### Document Permissions (Paradigm Only)

**Controlled in Paradigm:**
```javascript
// Paradigm document ACL
{
  "document_id": 12345,
  "filename": "contract_acme_2025.pdf",
  "permissions": {
    "owner": "alice@company.com",
    "readers": ["Legal", "Contract Analysis"],  // Teams from Paradigm
    "writers": ["alice@company.com"],
    "public": false
  }
}
```

**Enforced by Paradigm API:**
```python
# When n8n workflow tries to access document
GET /api/v2/files/12345
Authorization: Bearer lgn_sk_abc123  # Alice's API key

# Paradigm checks:
# - Is this API key valid?
# - Does alice@company.com have access to doc 12345?
# - Is she in "Legal" or "Contract Analysis" team?

# Returns: 200 OK (allowed) or 403 Forbidden
```

**n8n has NO control** over document access - Paradigm enforces at API level.

---

### Workflow Permissions (n8n with Paradigm Teams)

**Controlled in n8n:**
```javascript
// n8n workflow permissions
{
  "workflow_id": "wf_contract_analysis_123",
  "name": "Contract Analysis Workflow",
  "owner": "alice@company.com",
  "permissions": {
    "viewers": ["Legal"],           // Paradigm team
    "editors": ["Contract Analysis"], // Paradigm team
    "executors": ["Legal", "Finance"] // Multiple Paradigm teams
  }
}
```

**Key insight:** n8n uses **Paradigm team memberships** to enforce workflow permissions.

**Example:**
```
1. Bob (member of "Legal") logs into n8n
2. SAML tells n8n: groups=["Legal"]
3. n8n shows Bob all workflows where:
   - viewers includes "Legal"
   - editors includes "Legal"
   - executors includes "Legal"
4. Bob sees "Contract Analysis Workflow"
5. He can VIEW but not EDIT (only "Contract Analysis" team can edit)
```

---

## 5. SSO: Paradigm is Identity Provider

### SAML Flow Detailed

```
┌─────────┐                   ┌──────────┐                  ┌─────────┐
│  User   │                   │ Paradigm │                  │   n8n   │
│ Browser │                   │   (IdP)  │                  │   (SP)  │
└────┬────┘                   └────┬─────┘                  └────┬────┘
     │                             │                             │
     │ 1. Visit n8n                │                             │
     │────────────────────────────────────────────────────────>│
     │                             │                             │
     │ 2. Redirect to Paradigm SSO │                             │
     │<────────────────────────────────────────────────────────│
     │  (SAML AuthnRequest)        │                             │
     │                             │                             │
     │ 3. Authenticate with Paradigm                             │
     │────────────────────────────>│                             │
     │  (or use existing session)  │                             │
     │                             │                             │
     │                          4. Paradigm validates user       │
     │                             │ - Checks credentials        │
     │                             │ - Loads user profile        │
     │                             │ - Loads team memberships    │
     │                             │ - Retrieves API key         │
     │                             │                             │
     │ 5. SAML Assertion           │                             │
     │<────────────────────────────│                             │
     │  (includes user data + API key)                           │
     │                             │                             │
     │ 6. POST assertion to n8n    │                             │
     │────────────────────────────────────────────────────────>│
     │                             │                             │
     │                             │                          7. n8n validates
     │                             │                             │ - Signature
     │                             │                             │ - Certificate
     │                             │                             │ - Timestamp
     │                             │                             │
     │                             │                          8. n8n creates/updates user
     │                             │                             │ - Email, name
     │                             │                             │ - Teams
     │                             │                             │ - Stores API key
     │                             │                             │
     │ 9. Logged into n8n          │                             │
     │<────────────────────────────────────────────────────────│
     │                             │                             │
```

**Who controls what:**

| Action | Controlled By |
|--------|---------------|
| User authentication | Paradigm |
| Password validation | Paradigm |
| MFA/2FA | Paradigm |
| Session timeout | Paradigm (for SSO session) |
| User profile data | Paradigm |
| Team memberships | Paradigm |
| API key issuance | Paradigm |
| SAML assertion signing | Paradigm |
| n8n session creation | n8n (after validating SAML) |
| Workflow access control | n8n (using Paradigm teams) |

---

## 6. API Keys: Paradigm Owns, n8n Stores

### API Key Lifecycle

**Creation (Paradigm):**
```python
# When user is created in Paradigm
user = paradigm.users.create(
    email="alice@company.com",
    team="Legal"
)

# Paradigm auto-generates API key
api_key = "lgn_sk_abc123..."
paradigm.store_api_key(user.id, api_key)
```

**Transmission (SAML):**
```xml
<!-- Paradigm sends to n8n during SSO -->
<saml:Attribute Name="paradigm_api_key">
  <saml:AttributeValue>lgn_sk_abc123...</saml:AttributeValue>
</saml:Attribute>
```

**Storage (n8n):**
```javascript
// n8n stores in encrypted credential vault
{
  "credential_id": "cred_xyz789",
  "user_id": "alice@company.com",
  "type": "paradigmApi",
  "name": "Paradigm API (Personal)",
  "data_encrypted": "AES256(...)",  // Contains: lgn_sk_abc123...
  "source": "paradigm_sso",
  "auto_updated": true  // Updates on each SAML login
}
```

**Rotation (Paradigm):**
```python
# Admin rotates Alice's API key in Paradigm
new_key = paradigm.rotate_api_key(user_id="user_123")
# Returns: lgn_sk_xyz789...

# Next time Alice logs into n8n:
# - SAML includes new key
# - n8n updates stored credential automatically
# - Old key no longer works
```

**Revocation (Paradigm):**
```python
# User leaves company - Paradigm revokes key
paradigm.revoke_api_key(user_id="user_123")

# Immediate effect:
# - API calls with old key return 401 Unauthorized
# - n8n workflows using that key fail
# - Next SAML login: no API key in assertion (user disabled)
```

---

## 7. Synchronization Methods

### Option A: SAML Only (Just-in-Time Provisioning)

**How it works:**
- User data synced ONLY when user logs in
- No background sync process
- Simple but can be stale

**Pros:**
- ✅ Simple setup
- ✅ No additional services needed
- ✅ Works out of the box with n8n Enterprise

**Cons:**
- ❌ Users not synced until they log in
- ❌ Team changes don't apply until next login
- ❌ Can't pre-provision users

**Good for:** Small deployments (<100 users), infrequent changes

---

### Option B: SAML + SCIM (Real-Time Sync)

**SCIM = System for Cross-domain Identity Management**

**How it works:**
```
Paradigm detects change → Sends SCIM API call → n8n updates user
```

**Example: User added to team**
```http
# Paradigm sends to n8n
PATCH https://n8n.company.com/scim/v2/Users/alice@company.com
Content-Type: application/scim+json
Authorization: Bearer scim_token_abc123

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "add",
      "path": "groups",
      "value": [
        {
          "value": "team_finance_012",
          "display": "Finance"
        }
      ]
    }
  ]
}
```

**n8n immediately updates:**
- Alice is now member of "Finance" team
- She can access Finance workflows
- No need to wait for next login

**Pros:**
- ✅ Real-time sync
- ✅ Can pre-provision users
- ✅ Immediate team/role updates
- ✅ Industry standard (SCIM 2.0)

**Cons:**
- ❌ More complex setup
- ❌ Requires SCIM server in Paradigm
- ❌ n8n Enterprise feature (not in free version)

**Good for:** Large deployments (>100 users), frequent org changes

---

## 8. What Admin Manages Where

### Paradigm Admin Console

**User Management:**
- ✅ Create/disable users
- ✅ Assign users to teams
- ✅ Set user roles (analyst, admin, etc.)
- ✅ Reset passwords
- ✅ Manage MFA
- ✅ Rotate API keys
- ✅ View user activity logs

**Team Management:**
- ✅ Create/delete teams
- ✅ Set team hierarchy (parent/child)
- ✅ Assign team permissions (document access)
- ✅ Set team quotas (API calls, storage)

**SSO Configuration:**
- ✅ Configure SAML settings
- ✅ Upload certificates
- ✅ Map attributes to claims
- ✅ Configure session timeout

**Document Permissions:**
- ✅ Set document ACLs
- ✅ Share documents with teams
- ✅ Manage public/private access

---

### n8n Admin Console

**Workflow Management:**
- ✅ View all workflows
- ✅ Assign workflow ownership
- ✅ Set workflow permissions (who can view/edit)
- ✅ Archive/delete workflows
- ✅ View execution history

**Local Team Management (optional):**
- ✅ Create n8n-only teams (for workflow organization)
  - Example: "Workflow Reviewers" (not a Paradigm team)
- ❌ Cannot modify Paradigm-sourced teams

**Credential Management:**
- ✅ View user credentials (encrypted)
- ✅ Manage shared credentials (e.g., shared Paradigm API key)
- ❌ Cannot modify personal credentials (from SAML)

**Monitoring:**
- ✅ View execution logs
- ✅ Set up alerts
- ✅ Monitor system health

**SSO Configuration (read-only):**
- ✅ View SAML settings
- ❌ Cannot change IdP URL (must match Paradigm)

---

## 9. Decision Tree: Where to Make Changes

```
┌─────────────────────────────────────────────────┐
│ What do you want to change?                    │
└───────────────────┬─────────────────────────────┘
                    │
        ┌───────────┴───────────────────────┐
        │                                   │
    ┌───▼────┐                        ┌─────▼─────┐
    │ User?  │                        │ Workflow? │
    └───┬────┘                        └─────┬─────┘
        │                                   │
        ├─ Add/remove user                 ├─ Create workflow
        │  → Paradigm Admin                │  → n8n (user or admin)
        │                                   │
        ├─ Change user's teams             ├─ Change workflow permissions
        │  → Paradigm Admin                │  → n8n Admin
        │                                   │
        ├─ Reset password                  ├─ Schedule workflow
        │  → Paradigm Admin                │  → n8n (user or admin)
        │                                   │
        └─ Rotate API key                  └─ View execution history
           → Paradigm Admin                   → n8n (user or admin)

┌─────────────────┐                  ┌──────────────────┐
│ Team/Group?     │                  │ Document Access? │
└───┬─────────────┘                  └─────┬────────────┘
    │                                      │
    ├─ Create/delete team                 ├─ Share document with team
    │  → Paradigm Admin                   │  → Paradigm (owner or admin)
    │                                      │
    ├─ Add/remove team members            ├─ Set document permissions
    │  → Paradigm Admin                   │  → Paradigm (owner or admin)
    │                                      │
    └─ Set team quotas                    └─ View who accessed document
       → Paradigm Admin                      → Paradigm Admin

┌──────────────────┐
│ SSO/Auth Config? │
└───┬──────────────┘
    │
    ├─ Change SSO settings
    │  → Paradigm Admin
    │
    ├─ Update SAML certificate
    │  → Paradigm Admin
    │
    └─ Configure MFA
       → Paradigm Admin
```

---

## 10. Example: Complete User Journey

### Alice's First 90 Days

**Day 1 - Onboarding:**
```
HR creates Alice in Paradigm:
  - Email: alice@company.com
  - Team: Legal
  - Role: Document Analyst

Paradigm auto-generates API key: lgn_sk_abc123...

Alice receives welcome email:
  "Login to Paradigm: https://paradigm.company.com"
  "Login to Workflows: https://workflows.company.com"
  "Both use same credentials (SSO)"
```

**Day 1 - First n8n Login:**
```
1. Alice visits workflows.company.com
2. Clicks "Login with Paradigm SSO"
3. Enters credentials at Paradigm
4. Redirected back to n8n
5. n8n auto-creates her account:
   - Teams: Legal
   - Credential: Paradigm API (Personal)
6. She sees workflows shared with "Legal" team
```

**Week 2 - Promoted to Senior Analyst:**
```
Manager updates in Paradigm:
  - Role: Document Analyst → Senior Document Analyst
  - Adds to team: "Contract Analysis"

Next login to n8n:
  - SAML includes new team
  - Alice now sees "Contract Analysis" workflows
  - Can edit workflows (new role permissions)
```

**Month 3 - Switches Department:**
```
HR updates in Paradigm:
  - Team: Legal → Finance
  - Removes from: "Contract Analysis"

Next login to n8n:
  - Teams updated: Finance
  - Can access Finance workflows
  - Cannot access Legal workflows anymore
  - Her old workflows: still owned by her, but only Finance can see them
```

**Throughout - All Changes Made in Paradigm:**
- HR never touches n8n
- n8n automatically syncs via SAML
- Alice doesn't notice anything - seamless experience

---

## 11. Troubleshooting: Common Scenarios

### Scenario: User Can't Access Document in Workflow

**Symptom:**
```
Workflow fails with:
Error: 403 Forbidden - User does not have access to document 12345
```

**Where to check:**
1. ✅ **Paradigm** - Does user's team have access to the document?
   - Login to Paradigm → Documents → Check permissions
2. ✅ **Paradigm** - Is user's API key valid and not expired?
   - Paradigm → Users → alice@company.com → API Keys
3. ✅ **n8n** - Is workflow using correct credential?
   - n8n → Workflow → Nodes → Check credential selection

**Fix location: Paradigm** (share document with user's team)

---

### Scenario: User Can't See Workflow in n8n

**Symptom:**
```
Alice logs into n8n but doesn't see "Finance Workflow"
```

**Where to check:**
1. ✅ **Paradigm** - Is Alice member of Finance team?
   - Paradigm → Users → alice@company.com → Teams
2. ✅ **n8n** - Are teams synced?
   - n8n → User Profile → Check teams
   - If stale: Have Alice log out and log in again (refreshes SAML)
3. ✅ **n8n** - Is workflow shared with Finance team?
   - n8n → Workflow Settings → Permissions → Check viewers

**Fix location:**
- If team membership wrong: **Paradigm**
- If workflow permissions wrong: **n8n**

---

### Scenario: User's API Key Stopped Working

**Symptom:**
```
All workflows suddenly failing with:
Error: 401 Unauthorized - Invalid API key
```

**Where to check:**
1. ✅ **Paradigm** - Was API key rotated or revoked?
   - Paradigm → Users → alice@company.com → API Keys
2. ✅ **n8n** - Is stored credential stale?
   - Have user log out and log in (SAML refreshes API key)

**Fix location: Paradigm** (if key was accidentally revoked) or wait for next login (auto-sync)

---

## 12. Architecture Best Practices

### ✅ DO:

**Use Paradigm as single source of truth for:**
- User identity
- Team memberships
- Roles and permissions (for documents)
- API keys
- Authentication

**Use n8n for:**
- Workflow definitions
- Workflow execution
- Workflow-specific permissions (who can edit this workflow)
- Execution logs

**Sync regularly:**
- Use SCIM if available (real-time)
- Or: Force re-login periodically (daily/weekly) to refresh SAML data

---

### ❌ DON'T:

**Don't create users directly in n8n:**
- Always create in Paradigm first
- Let SAML/SCIM sync to n8n

**Don't modify Paradigm-sourced teams in n8n:**
- n8n can have local teams, but don't edit synced teams
- Changes will be overwritten on next sync

**Don't store API keys outside Paradigm:**
- Paradigm controls key lifecycle
- n8n stores keys, but doesn't manage them

**Don't give n8n admin permissions to Paradigm:**
- n8n shouldn't be able to create Paradigm users
- One-way flow: Paradigm → n8n

---

## Summary: The Golden Rule

```
╔════════════════════════════════════════════════╗
║  PARADIGM MANAGES PEOPLE                       ║
║  N8N MANAGES WORKFLOWS                         ║
║                                                ║
║  Data flows: Paradigm → n8n (not reverse)     ║
╚════════════════════════════════════════════════╝
```

**What Paradigm owns:**
- 👥 Users
- 👥 Teams/Groups
- 🔑 API Keys
- 🔐 SSO/Authentication
- 📄 Document Permissions
- 📊 Quotas

**What n8n owns:**
- 🔄 Workflows
- 📋 Execution History
- ⚙️ Workflow Permissions (using Paradigm teams)
- 📝 Workflow Schedules

**What's shared:**
- 👥 Team memberships (Paradigm creates, n8n consumes)
- 🔑 API keys (Paradigm generates, n8n stores)
- 🎫 SSO sessions (Paradigm authenticates, n8n validates)

---

## Quick Reference Card

| I want to... | System | Role Required |
|--------------|--------|---------------|
| Add a new user | Paradigm | Paradigm Admin |
| Create a team | Paradigm | Paradigm Admin |
| Assign user to team | Paradigm | Paradigm Admin |
| Rotate someone's API key | Paradigm | Paradigm Admin |
| Give user access to document | Paradigm | Document Owner |
| Create a workflow | n8n | n8n User |
| Share workflow with team | n8n | Workflow Owner |
| Schedule workflow | n8n | n8n User |
| View execution logs | n8n | n8n User/Admin |
| Change SSO settings | Paradigm | Paradigm Admin |
| Reset user password | Paradigm | Paradigm Admin |

**Admin tip:** If you're managing both systems, spend 90% of time in Paradigm for user/team management, 10% in n8n for workflow troubleshooting.
