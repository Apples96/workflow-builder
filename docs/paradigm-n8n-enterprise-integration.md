# Paradigm + n8n Enterprise Integration Architecture

## Executive Summary

This document outlines how n8n can integrate with Paradigm for enterprise customers, enabling SSO authentication and per-user API key management without LightOn commercializing n8n directly.

**Business Model:**
- LightOn provides Paradigm API + custom n8n nodes (open source)
- Customer purchases n8n Enterprise license directly from n8n.io
- Customer purchases Paradigm Enterprise from LightOn
- Integration happens via SSO and API key federation

---

## 1. License and Commercial Model

### What LightOn Provides (Free/Open Source):
✅ **Custom n8n Community Nodes** for Paradigm API
- Published as `n8n-nodes-paradigm` on npm
- Apache 2.0 or MIT license
- Available in n8n community node marketplace
- Maintained by LightOn

✅ **Integration Documentation**
- SSO setup guide
- API key management guide
- Reference deployment architectures
- Best practices

✅ **Reference Deployment**
- Docker Compose templates
- Kubernetes manifests
- Example workflows

### What Customer Purchases Directly:

**From n8n.io:**
- **n8n Enterprise License** (~$500-$1000/user/year)
  - SSO/SAML support
  - RBAC (role-based access control)
  - Audit logging
  - SLA support
  - Advanced security features

**From LightOn:**
- **Paradigm Enterprise API**
  - SSO/SAML integration
  - Multi-tenant isolation
  - Per-user API keys
  - Enterprise SLA
  - Support

### Why This Works:
- LightOn doesn't resell n8n (avoids licensing issues)
- Customer gets direct support from both vendors
- LightOn differentiates through Paradigm nodes + integration expertise
- n8n gets more enterprise customers
- Win-win partnership

---

## 2. Enterprise Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Enterprise Customer                       │
│                                                              │
│  ┌──────────────┐                    ┌──────────────┐       │
│  │   Employee   │                    │   Employee   │       │
│  │   (Alice)    │                    │    (Bob)     │       │
│  └──────┬───────┘                    └──────┬───────┘       │
│         │                                   │               │
│         │  1. Login with SSO                │               │
│         └───────────┬───────────────────────┘               │
│                     ↓                                        │
│         ┌─────────────────────────┐                         │
│         │   Identity Provider     │                         │
│         │  (Paradigm Enterprise)  │                         │
│         │  - SAML 2.0 IdP         │                         │
│         │  - User directory       │                         │
│         │  - API key management   │                         │
│         └───────────┬─────────────┘                         │
│                     │ 2. SAML assertion                     │
│                     │    (with API key claim)               │
│                     ↓                                        │
│         ┌─────────────────────────┐                         │
│         │   n8n Enterprise        │                         │
│         │  - SAML 2.0 SP          │                         │
│         │  - User-specific creds  │                         │
│         │  - Workflow engine      │                         │
│         └───────────┬─────────────┘                         │
│                     │ 3. Execute workflow                   │
│                     │    with user's API key                │
│                     ↓                                        │
│         ┌─────────────────────────┐                         │
│         │   Paradigm API          │                         │
│         │  - Document processing  │                         │
│         │  - Per-user quotas      │                         │
│         │  - Audit logs           │                         │
│         └─────────────────────────┘                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. SSO Integration (SAML 2.0)

### Step 1: Paradigm as Identity Provider (IdP)

**Paradigm needs to provide:**
```xml
<!-- SAML 2.0 IdP Metadata -->
<EntityDescriptor entityID="https://paradigm.company.com/saml/metadata">
  <IDPSSODescriptor>
    <SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://paradigm.company.com/saml/sso"/>
    <SingleLogoutService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://paradigm.company.com/saml/slo"/>
  </IDPSSODescriptor>
</EntityDescriptor>
```

**SAML Assertion includes custom claims:**
```xml
<saml:AttributeStatement>
  <saml:Attribute Name="email">
    <saml:AttributeValue>alice@company.com</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="paradigm_api_key">
    <saml:AttributeValue>lgn_sk_abc123...</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="paradigm_user_id">
    <saml:AttributeValue>user_789</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="roles">
    <saml:AttributeValue>paradigm:document_analyst</saml:AttributeValue>
    <saml:AttributeValue>paradigm:workflow_builder</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
```

### Step 2: n8n as Service Provider (SP)

**n8n Enterprise configuration:**
```javascript
// n8n Enterprise environment variables
{
  // SSO Configuration
  "N8N_SSO_SAML_ENABLED": true,
  "N8N_SSO_SAML_IDP_METADATA_URL": "https://paradigm.company.com/saml/metadata",
  "N8N_SSO_SAML_ENTITY_ID": "https://workflows.company.com/saml",
  "N8N_SSO_SAML_ACS_URL": "https://workflows.company.com/rest/sso/saml/acs",

  // Attribute mapping
  "N8N_SSO_SAML_ATTRIBUTE_EMAIL": "email",
  "N8N_SSO_SAML_ATTRIBUTE_FIRST_NAME": "givenName",
  "N8N_SSO_SAML_ATTRIBUTE_LAST_NAME": "surname",

  // Custom attribute for API key
  "N8N_SSO_SAML_ATTRIBUTE_PARADIGM_KEY": "paradigm_api_key",

  // Role-based access control
  "N8N_SSO_SAML_ROLE_MAPPING": {
    "paradigm:admin": "n8n:admin",
    "paradigm:workflow_builder": "n8n:editor",
    "paradigm:document_analyst": "n8n:viewer"
  }
}
```

### Step 3: User Login Flow

```
1. User visits n8n: https://workflows.company.com
   → Redirected to Paradigm SSO login

2. User authenticates with Paradigm:
   - Username/password
   - OR existing Paradigm session (already logged in)
   - OR corporate SSO (Azure AD, Okta, etc.)

3. Paradigm creates SAML assertion:
   - Includes user email, name, roles
   - **CRITICAL**: Includes user's Paradigm API key as custom claim

4. User redirected back to n8n with SAML response

5. n8n validates SAML assertion:
   - Signature verification
   - Certificate validation
   - Timestamp check

6. n8n creates user session:
   - Extracts email, roles
   - **CRITICAL**: Stores Paradigm API key in user's credential vault

7. User lands in n8n dashboard:
   - Sees workflows they have access to
   - Their Paradigm API key is automatically available
```

---

## 4. Per-User API Key Management

### Option A: API Key in SAML Assertion (Recommended)

**Pros:**
- ✅ Seamless user experience
- ✅ No manual API key entry
- ✅ Keys sync automatically from Paradigm
- ✅ Centralized key rotation (rotate in Paradigm, auto-updates in n8n)

**Implementation:**

1. **Paradigm stores API keys per user:**
```sql
-- Paradigm database
CREATE TABLE user_api_keys (
  user_id UUID PRIMARY KEY,
  api_key_encrypted TEXT NOT NULL,  -- lgn_sk_...
  created_at TIMESTAMP,
  last_rotated TIMESTAMP,
  expires_at TIMESTAMP
);
```

2. **Paradigm includes API key in SAML assertion** (see above)

3. **n8n custom middleware** intercepts SAML login and stores key:
```typescript
// n8n custom hook (requires n8n Enterprise + custom code)
import { User } from 'n8n-core';
import { CredentialsHelper } from 'n8n-workflow';

export class ParadigmSamlHandler {
  async onSamlLogin(samlAttributes: any, user: User) {
    // Extract API key from SAML assertion
    const paradigmApiKey = samlAttributes['paradigm_api_key'];

    if (!paradigmApiKey) {
      throw new Error('Paradigm API key not provided in SAML assertion');
    }

    // Store in user's credential vault
    const credentialData = {
      name: 'Paradigm API (Personal)',
      type: 'paradigmApi',
      data: {
        apiKey: paradigmApiKey,
        baseUrl: 'https://paradigm.lighton.ai'
      }
    };

    // Create or update credential for this user
    await CredentialsHelper.createOrUpdateCredential(
      user.id,
      'paradigm-personal-key',
      credentialData
    );

    console.log(`Stored Paradigm API key for user ${user.email}`);
  }
}
```

4. **In workflows, users select their personal credential:**
```
[Paradigm Document Search Node]
┌────────────────────────────┐
│ Credential:                │
│ ● Paradigm API (Personal)  │ ← Auto-populated from SAML
│   (alice@company.com)      │
│                            │
│ ○ Paradigm API (Shared)    │ ← Optional shared key
└────────────────────────────┘
```

---

### Option B: OAuth 2.0 Token Exchange (More Secure)

**Flow:**
```
1. User logs into n8n via Paradigm SSO
2. n8n receives OAuth access token (short-lived, 1 hour)
3. Workflows use access token to call Paradigm API
4. Token expires → n8n refreshes automatically
5. User logs out → token revoked immediately
```

**Implementation:**

1. **Paradigm implements OAuth 2.0 Authorization Server:**
```
POST https://paradigm.company.com/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:saml2-bearer
assertion=<SAML_ASSERTION>
scope=paradigm:documents:read paradigm:documents:write

Response:
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "refresh_abc123",
  "scope": "paradigm:documents:read paradigm:documents:write"
}
```

2. **n8n Paradigm nodes use OAuth token:**
```typescript
// Modified Paradigm node to support OAuth
export class ParadigmDocumentSearch implements INodeType {
  async execute(this: IExecuteFunctions) {
    const credentials = await this.getCredentials('paradigmApi');

    // Check if using OAuth or API key
    const authHeader = credentials.oauthToken
      ? `Bearer ${credentials.oauthToken}`
      : `Bearer ${credentials.apiKey}`;

    const response = await this.helpers.request({
      method: 'POST',
      url: 'https://paradigm.lighton.ai/api/v2/chat/completions',
      headers: {
        'Authorization': authHeader
      },
      body: {...}
    });

    return [this.helpers.returnJsonArray(response)];
  }
}
```

**Pros:**
- ✅ More secure (short-lived tokens)
- ✅ Immediate revocation on logout
- ✅ Fine-grained scopes (read vs write)

**Cons:**
- ❌ Paradigm must implement full OAuth 2.0 server
- ❌ More complex setup

---

## 5. Multi-Tenancy and Isolation

### Scenario: Multiple Departments Using Same n8n Instance

**Requirements:**
- Legal department sees only their workflows
- Finance department sees only their workflows
- No cross-department data access
- Shared templates available to all

**n8n Enterprise RBAC:**
```javascript
{
  "teams": [
    {
      "name": "Legal",
      "users": ["alice@company.com", "bob@company.com"],
      "permissions": {
        "workflows": "own_team_only",
        "credentials": "own_team_only",
        "executions": "own_team_only"
      }
    },
    {
      "name": "Finance",
      "users": ["charlie@company.com"],
      "permissions": {
        "workflows": "own_team_only",
        "credentials": "own_team_only",
        "executions": "own_team_only"
      }
    },
    {
      "name": "Workflow Admins",
      "users": ["admin@company.com"],
      "permissions": {
        "workflows": "all",
        "credentials": "all",
        "executions": "all",
        "settings": "full"
      }
    }
  ],

  "sharedResources": {
    "templates": [
      "contract-analysis-template",
      "invoice-extraction-template"
    ]
  }
}
```

**Paradigm API quotas per team:**
```javascript
// Paradigm tracks usage per user/team
{
  "user_id": "alice@company.com",
  "team": "Legal",
  "quotas": {
    "document_searches_per_day": 1000,
    "documents_analyzed_per_month": 5000,
    "storage_gb": 100
  },
  "current_usage": {
    "document_searches_today": 234,
    "documents_analyzed_this_month": 1892,
    "storage_gb": 47.3
  }
}
```

---

## 6. Audit Logging and Compliance

### What Gets Logged:

**In n8n:**
```json
{
  "timestamp": "2025-02-22T14:30:00Z",
  "event": "workflow_executed",
  "user": "alice@company.com",
  "workflow_id": "wf_abc123",
  "workflow_name": "Contract Analysis - Legal",
  "execution_id": "exec_xyz789",
  "status": "success",
  "duration_ms": 3421,
  "nodes_executed": 7,
  "credentials_used": [
    {
      "type": "paradigmApi",
      "name": "Paradigm API (Personal)",
      "user": "alice@company.com"
    }
  ]
}
```

**In Paradigm:**
```json
{
  "timestamp": "2025-02-22T14:30:05Z",
  "api_endpoint": "/api/v2/chat/completions",
  "user_id": "alice@company.com",
  "api_key_id": "key_abc...",
  "request": {
    "file_ids": [12345, 67890],
    "query": "Extract buyer and seller information",
    "guided_json": {...}
  },
  "response_status": 200,
  "tokens_used": 1843,
  "processing_time_ms": 2341,
  "source_system": "n8n",
  "source_workflow": "wf_abc123"
}
```

**Cross-referencing:**
- Both systems log execution IDs
- Can correlate n8n workflow → Paradigm API calls
- Full audit trail for compliance (GDPR, SOC2, etc.)

---

## 7. Reference Deployment Architecture

### Enterprise Production Setup

```yaml
version: '3.8'

services:
  # n8n Enterprise (customer manages)
  n8n:
    image: n8nio/n8n-enterprise:latest
    ports:
      - "5678:5678"
    environment:
      # Database
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n
      - DB_POSTGRESDB_PASSWORD=${N8N_DB_PASSWORD}

      # SSO/SAML
      - N8N_SSO_SAML_ENABLED=true
      - N8N_SSO_SAML_IDP_METADATA_URL=https://paradigm.company.com/saml/metadata

      # License
      - N8N_LICENSE_KEY=${N8N_ENTERPRISE_LICENSE}

      # Security
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - N8N_USER_MANAGEMENT_JWT_SECRET=${JWT_SECRET}

      # Logging
      - N8N_LOG_LEVEL=info
      - N8N_LOG_OUTPUT=file,console

    volumes:
      - n8n_data:/home/node/.n8n
      - ./custom-nodes/n8n-nodes-paradigm:/home/node/.n8n/custom
    depends_on:
      - postgres
      - redis

  # PostgreSQL for n8n
  postgres:
    image: postgres:14-alpine
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD=${N8N_DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis for queue management
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  # Paradigm Integration Service (optional)
  paradigm-sync:
    build: ./paradigm-sync-service
    environment:
      - PARADIGM_ADMIN_KEY=${PARADIGM_ADMIN_KEY}
      - N8N_API_KEY=${N8N_API_KEY}
    # Syncs users, teams, quotas between Paradigm and n8n

volumes:
  n8n_data:
  postgres_data:
  redis_data:
```

---

## 8. User Provisioning Flow

### Automatic User Sync

**When new employee joins company:**

```
1. Admin creates Paradigm account:
   - Email: newuser@company.com
   - Role: Document Analyst
   - Team: Legal
   - → Paradigm auto-generates API key

2. User logs into n8n for first time:
   - Clicks "Login with Paradigm SSO"
   - Redirected to Paradigm
   - Authenticates
   - SAML assertion includes API key
   - Redirected back to n8n

3. n8n receives SAML assertion:
   - Creates user account automatically (JIT provisioning)
   - Assigns roles based on SAML attributes
   - Stores API key in credential vault
   - User lands in dashboard

4. User's first workflow:
   - Drags "Paradigm Document Search" node
   - Credential auto-selected: "Paradigm API (Personal)"
   - Works immediately - no manual setup!
```

**When employee leaves company:**

```
1. Admin disables Paradigm account
   → API key revoked immediately

2. Next time ex-employee tries to use n8n:
   - Workflows fail (API key invalid)
   - SSO login fails (account disabled)

3. n8n admin removes user:
   - All personal workflows archived
   - Shared workflows reassigned
   - Audit logs preserved
```

---

## 9. Security Considerations

### API Key Storage

**Bad: Plaintext in n8n database**
```sql
-- DON'T DO THIS
SELECT * FROM credentials WHERE user_id = 123;
-- Returns: {"apiKey": "lgn_sk_abc123..."}
```

**Good: Encrypted at rest**
```sql
-- n8n Enterprise does this automatically
SELECT * FROM credentials WHERE user_id = 123;
-- Returns: {"apiKey": "ENCRYPTED_BLOB_AES256..."}
```

**Better: Encrypted + short-lived**
```javascript
// Use OAuth tokens that expire
{
  "access_token": "eyJhbGc...",  // Expires in 1 hour
  "refresh_token": "refresh_...", // Expires in 7 days
  "encrypted_with": "AES-256-GCM",
  "key_derivation": "PBKDF2"
}
```

### Network Security

```
┌────────────────────────────────────────┐
│         Corporate Network              │
│                                        │
│  ┌──────────┐    ┌──────────┐         │
│  │ Employee │───▶│ n8n (VPC)│         │
│  │ Browser  │    │ Internal │         │
│  └──────────┘    └─────┬────┘         │
│                        │               │
│              ┌─────────▼─────────┐     │
│              │  Firewall/NAT     │     │
│              │  - Whitelist IPs  │     │
│              │  - Rate limiting  │     │
│              └─────────┬─────────┘     │
│                        │               │
└────────────────────────┼───────────────┘
                         │ HTTPS only
                         │ TLS 1.3
                         ▼
           ┌──────────────────────────┐
           │   Paradigm API (Cloud)   │
           │   paradigm.lighton.ai    │
           └──────────────────────────┘
```

### Compliance

**GDPR:**
- ✅ User data stays in EU (if Paradigm deployed in EU)
- ✅ User can export all workflows (n8n data export)
- ✅ User can request deletion (GDPR workflow)
- ✅ Audit logs for data processing activities

**SOC 2:**
- ✅ All API calls logged
- ✅ Access control (RBAC)
- ✅ Encryption at rest and in transit
- ✅ Regular security audits

---

## 10. Cost Model for Customer

### Example: 100-person company

**n8n Enterprise License:**
- 100 users × $50/user/month = $5,000/month
- OR: 20 workflow builders × $100/user/month = $2,000/month
  - (Viewers free, only builders pay)

**Paradigm Enterprise:**
- Based on LightOn's pricing model
- Estimated: $10,000-$30,000/month depending on usage

**Infrastructure:**
- Server/VM: $500/month (AWS/Azure)
- PostgreSQL: $200/month
- Monitoring/logging: $100/month

**Total: ~$13,000-$38,000/month for 100 users**

---

## 11. LightOn's Role (Without Commercializing n8n)

### What LightOn Provides:

1. **Custom n8n Nodes (Free, Open Source)**
   - Published on npm and n8n marketplace
   - Maintained by LightOn
   - Apache 2.0 license

2. **Integration Services (Professional Services)**
   - SSO setup and configuration: €5,000-€10,000
   - Custom workflow development: €1,000/day
   - Training and enablement: €3,000/session
   - Ongoing support: €2,000/month

3. **Reference Architectures**
   - Deployment guides
   - Best practices
   - Security hardening
   - Compliance templates

4. **Paradigm Enterprise Features**
   - SAML IdP functionality
   - Per-user API key management
   - Team/department isolation
   - Usage quotas and billing

### Revenue Model for LightOn:

**Direct:**
- Paradigm API usage (existing business)
- Professional services for integration
- Support contracts

**Indirect:**
- More Paradigm customers (easier to adopt)
- Stickiness (workflows = lock-in)
- Upsell to Paradigm Enterprise (SSO requires it)

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Month 1)
- [ ] Develop 11 Paradigm n8n nodes
- [ ] Publish to npm and n8n marketplace
- [ ] Document SSO integration requirements
- [ ] Build reference Docker deployment

### Phase 2: Paradigm SSO (Month 2)
- [ ] Implement SAML IdP in Paradigm
- [ ] Add API key claims to SAML assertions
- [ ] Test with n8n Enterprise trial
- [ ] Document user provisioning flow

### Phase 3: Pilot Customer (Month 3)
- [ ] Select pilot customer (ideally existing Paradigm Enterprise)
- [ ] Customer purchases n8n Enterprise license
- [ ] Deploy integrated solution
- [ ] Train users
- [ ] Gather feedback

### Phase 4: Production Rollout (Month 4+)
- [ ] Iterate based on pilot feedback
- [ ] Create customer onboarding playbook
- [ ] Train LightOn support team
- [ ] Market to existing Paradigm customers

---

## 13. Competitive Positioning

### LightOn's Pitch:

> "Paradigm Enterprise now integrates seamlessly with n8n, the leading open-source workflow automation platform. Your employees can build and schedule document processing workflows visually - no coding required. Single sign-on means they're automatically authenticated with their personal Paradigm API keys. Deploy on-premise for full control, or use our managed option."

**Key differentiators:**
1. **Pre-built Paradigm nodes** (competitors would need to build from scratch)
2. **SSO integration** (seamless UX)
3. **Per-user API keys** (proper isolation and quotas)
4. **LightOn professional services** (we know both systems)
5. **Reference deployments** (faster time to value)

### Why Customers Choose This:

- ✅ Best-of-breed: n8n for workflows, Paradigm for documents
- ✅ No vendor lock-in (both are portable)
- ✅ Enterprise-grade security (SSO, RBAC, audit logs)
- ✅ Cost-effective (compared to building custom)
- ✅ Proven technology (not beta/experimental)

---

## Conclusion

**Can LightOn and n8n integrate for enterprise customers?**

**Yes, absolutely.** Here's how:

1. **LightOn provides:**
   - Free, open-source Paradigm nodes for n8n
   - SSO integration (Paradigm as IdP)
   - Professional services and support

2. **Customer purchases:**
   - n8n Enterprise license (directly from n8n.io)
   - Paradigm Enterprise (from LightOn)

3. **Integration works via:**
   - SAML 2.0 SSO (user logs in once, works in both systems)
   - Per-user API keys (passed via SAML claims)
   - Shared audit logs and compliance

4. **Result:**
   - Employees build workflows visually in n8n
   - Workflows call Paradigm API with their personal API keys
   - Full enterprise features: SSO, RBAC, audit logs, quotas

**No licensing conflict** - LightOn doesn't resell n8n, just provides integration and nodes.

**Win-win-win:**
- **LightOn:** More Paradigm adoption, services revenue
- **n8n:** More enterprise customers
- **Customer:** Best-of-breed solution without vendor lock-in
