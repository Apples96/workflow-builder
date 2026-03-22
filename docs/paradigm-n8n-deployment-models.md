# Paradigm + n8n: Deployment Models and Multi-Tenancy

## Question 1: Customer Has Their Own n8n Instance

### Challenge

Customer already runs n8n (maybe for other integrations like Slack, databases, etc.). How does LightOn integrate Paradigm and enforce the proper architecture?

---

### Scenario A: Customer's Existing n8n Setup

**What they have:**
```
Customer's n8n instance:
  • SSO: Azure AD / Okta / Google Workspace
  • Users: 200 employees
  • Workflows: 150 workflows (Slack, Salesforce, etc.)
  • Teams: Sales, Marketing, Engineering, etc.
  • Deployment: Self-hosted on AWS
```

**What LightOn needs to add:**
- Paradigm custom nodes (11 nodes)
- Paradigm SSO integration (for Paradigm users)
- Per-user Paradigm API keys

---

### Option 1: Dual SSO Configuration (Recommended)

**Architecture:**
```
┌─────────────────────────────────────────────┐
│        Customer's n8n Instance              │
│                                             │
│  SSO Providers:                             │
│  ┌────────────────────────────────────┐    │
│  │ 1. Azure AD (existing)             │    │
│  │    - Sales team                    │    │
│  │    - Marketing team                │    │
│  │    - Engineering team              │    │
│  └────────────────────────────────────┘    │
│                                             │
│  ┌────────────────────────────────────┐    │
│  │ 2. Paradigm SSO (new)              │    │
│  │    - Legal team                    │    │
│  │    - Compliance team               │    │
│  │    - Operations team               │    │
│  └────────────────────────────────────┘    │
│                                             │
│  All users in same n8n instance            │
└─────────────────────────────────────────────┘
```

**n8n Enterprise supports multiple SSO providers:**
```javascript
// n8n configuration
{
  "sso": {
    "providers": [
      {
        "type": "saml",
        "name": "Azure AD",
        "entityId": "https://login.microsoftonline.com/...",
        "loginButton": "Login with Azure AD"
      },
      {
        "type": "saml",
        "name": "Paradigm",
        "entityId": "https://paradigm.company.com/saml",
        "loginButton": "Login with Paradigm",
        "attributeMapping": {
          "email": "email",
          "groups": "groups",
          "paradigm_api_key": "paradigm_api_key"  // Custom claim
        }
      }
    ]
  }
}
```

**User experience:**
```
n8n login screen:
┌──────────────────────────────┐
│   Welcome to Company n8n     │
│                              │
│  [Login with Azure AD]       │ ← Existing users
│  [Login with Paradigm]       │ ← New Paradigm users
│                              │
│  Or use email/password       │
└──────────────────────────────┘
```

**Pros:**
- ✅ Minimal disruption to existing setup
- ✅ Users choose appropriate SSO
- ✅ Both user types in same n8n instance
- ✅ Can share workflows across SSO boundaries (if needed)

**Cons:**
- ❌ Some users might be confused by two login buttons
- ❌ Requires n8n Enterprise (not free tier)

---

### Option 2: Separate n8n Instance for Paradigm

**Architecture:**
```
┌────────────────────────────┐  ┌────────────────────────────┐
│  Existing n8n Instance     │  │  New Paradigm n8n Instance │
│  https://n8n.company.com   │  │  https://paradigm-n8n...   │
│                            │  │                            │
│  • Azure AD SSO            │  │  • Paradigm SSO            │
│  • Sales workflows         │  │  • Document workflows      │
│  • Marketing workflows     │  │  • Paradigm API only       │
│  • Slack, Salesforce, etc. │  │  • Legal/Compliance users  │
└────────────────────────────┘  └────────────────────────────┘
```

**Pros:**
- ✅ Complete isolation (security)
- ✅ No impact on existing setup
- ✅ Clear separation of concerns

**Cons:**
- ❌ Users need to access two different n8n instances
- ❌ Double the infrastructure cost
- ❌ Can't easily share workflows between instances

**When to use:** Customer values isolation OR existing n8n is heavily customized.

---

### Option 3: Add Paradigm Nodes to Existing Setup (Minimal Integration)

**Architecture:**
```
┌─────────────────────────────────────────────┐
│        Customer's n8n Instance              │
│                                             │
│  SSO: Azure AD (unchanged)                  │
│                                             │
│  Nodes:                                     │
│  • Existing: Slack, Salesforce, etc.       │
│  • New: 11 Paradigm nodes (installed)      │
│                                             │
│  Credentials:                               │
│  • Users manually add Paradigm API key     │
│    (no SSO integration)                    │
└─────────────────────────────────────────────┘
```

**Setup:**
1. Install Paradigm nodes: `npm install n8n-nodes-paradigm`
2. Users add Paradigm credential manually:
   ```
   n8n → Credentials → Add New
   Type: Paradigm API
   API Key: lgn_sk_abc123... (copied from Paradigm)
   ```

**Pros:**
- ✅ Simplest integration
- ✅ No SSO changes needed
- ✅ Works immediately

**Cons:**
- ❌ Manual API key management (not synced)
- ❌ Users must copy/paste API keys
- ❌ No automatic key rotation
- ❌ No per-user audit trail (shared keys possible)

**When to use:** Quick pilot, small team (<10 users), low security requirements.

---

### Enforcement Mechanisms for Customer-Owned n8n

**1. Pre-Flight Validation Script**

LightOn provides a script to check customer's n8n setup:

```bash
#!/bin/bash
# paradigm-n8n-validator.sh

echo "Validating n8n setup for Paradigm integration..."

# Check n8n version
N8N_VERSION=$(docker exec n8n n8n --version | grep -oP '[\d.]+')
REQUIRED_VERSION="1.0.0"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$N8N_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ n8n version $N8N_VERSION is too old. Requires $REQUIRED_VERSION+"
    exit 1
fi
echo "✅ n8n version: $N8N_VERSION"

# Check for n8n Enterprise (required for SSO)
if ! docker exec n8n env | grep -q "N8N_LICENSE"; then
    echo "⚠️  n8n Enterprise license not detected. SSO integration requires Enterprise."
    echo "   Consider Option 3 (manual credentials) or upgrade to Enterprise."
else
    echo "✅ n8n Enterprise detected"
fi

# Check if Paradigm nodes installed
if docker exec n8n npm list n8n-nodes-paradigm > /dev/null 2>&1; then
    echo "✅ Paradigm nodes already installed"
else
    echo "❌ Paradigm nodes not found. Run: npm install n8n-nodes-paradigm"
fi

# Check database type (PostgreSQL required for production)
if docker exec n8n env | grep -q "DB_TYPE=postgresdb"; then
    echo "✅ Using PostgreSQL database"
else
    echo "⚠️  Not using PostgreSQL. SQLite not recommended for production."
fi

# Check network connectivity to Paradigm API
if curl -s -o /dev/null -w "%{http_code}" https://paradigm.lighton.ai/health | grep -q "200"; then
    echo "✅ Can reach Paradigm API"
else
    echo "❌ Cannot reach Paradigm API. Check firewall/proxy settings."
fi

echo ""
echo "Validation complete. See above for any issues."
```

**2. Configuration Template**

LightOn provides pre-configured environment variables:

```bash
# paradigm-integration.env
# Add these to customer's n8n configuration

# Paradigm SSO (Option 1: Dual SSO)
N8N_SSO_SAML_PARADIGM_ENABLED=true
N8N_SSO_SAML_PARADIGM_IDP_URL=https://paradigm.customer.com/saml/metadata
N8N_SSO_SAML_PARADIGM_ATTRIBUTE_API_KEY=paradigm_api_key

# Or: Manual credentials (Option 3)
N8N_CUSTOM_EXTENSIONS=/custom-nodes
PARADIGM_NODES_VERSION=1.0.0
```

**3. Health Check Endpoint**

LightOn provides a health check workflow:

```javascript
// Import this workflow into customer's n8n
{
  "name": "Paradigm Integration Health Check",
  "nodes": [
    {
      "type": "n8n-nodes-base.schedule",
      "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}
    },
    {
      "type": "n8n-nodes-paradigm.healthCheck",
      "parameters": {}
    },
    {
      "type": "n8n-nodes-base.sendEmail",
      "parameters": {
        "subject": "Paradigm Integration Alert",
        "text": "{{ $json.status === 'unhealthy' ? 'Integration failed' : 'All OK' }}"
      }
    }
  ]
}
```

**4. Documentation and Training**

LightOn provides:
- Integration guide specific to customer's setup
- Best practices document
- Security checklist
- Troubleshooting guide
- Video walkthrough

**5. Support SLA**

LightOn support contract includes:
- Architecture review (before setup)
- Integration assistance (during setup)
- Quarterly health checks
- Priority support for Paradigm-related issues

**6. Certification Program**

Customer's n8n admin completes:
- "Paradigm + n8n Integration" certification (2-hour course)
- Proves they understand architecture
- Required for support SLA activation

---

## Question 2: LightOn-Hosted n8n Multi-Tenancy

### Challenge

If LightOn hosts n8n as a service, can one instance serve multiple customers, or does each customer need their own?

---

### Option A: Single Multi-Tenant Instance (Shared)

**Architecture:**
```
┌───────────────────────────────────────────────────────────┐
│         LightOn n8n Cloud (Single Instance)               │
│                                                           │
│  Customer A:                                              │
│  • Team: Acme Corp                                        │
│  • Users: alice@acme.com, bob@acme.com                    │
│  • Workflows: 50 (isolated to Acme Corp team)            │
│                                                           │
│  Customer B:                                              │
│  • Team: Widget Inc                                       │
│  • Users: charlie@widget.com                              │
│  • Workflows: 30 (isolated to Widget Inc team)           │
│                                                           │
│  Customer C:                                              │
│  • Team: Example LLC                                      │
│  • Users: dave@example.com                                │
│  • Workflows: 20 (isolated to Example LLC team)          │
│                                                           │
│  Shared Resources:                                        │
│  • Database: PostgreSQL (with row-level security)        │
│  • Redis: Queue management                                │
│  • Workers: Workflow execution pool                      │
└───────────────────────────────────────────────────────────┘
```

**How isolation works:**

1. **Team-based isolation (n8n native):**
```javascript
// Every resource tagged with team_id
{
  "workflow_id": "wf_123",
  "name": "Contract Analysis",
  "team_id": "team_acme_corp",  // ← Customer identifier
  "owner": "alice@acme.com"
}

// Database queries always filtered by team_id
SELECT * FROM workflows WHERE team_id = 'team_acme_corp';
```

2. **SSO per customer:**
```javascript
// n8n configuration
{
  "sso": {
    "providers": [
      {
        "name": "Acme Corp Paradigm",
        "entityId": "https://paradigm.acme.com/saml",
        "allowedDomains": ["acme.com"]  // Only @acme.com emails
      },
      {
        "name": "Widget Inc Paradigm",
        "entityId": "https://paradigm.widget.com/saml",
        "allowedDomains": ["widget.com"]
      }
    ]
  }
}
```

3. **Resource quotas per customer:**
```javascript
{
  "team_acme_corp": {
    "max_workflows": 100,
    "max_executions_per_day": 10000,
    "max_concurrent_executions": 50,
    "storage_gb": 100
  },
  "team_widget_inc": {
    "max_workflows": 50,
    "max_executions_per_day": 5000,
    "max_concurrent_executions": 25,
    "storage_gb": 50
  }
}
```

**Pros:**
- ✅ **Cost-efficient**: Single infrastructure for all customers
- ✅ **Easy maintenance**: One instance to update/patch
- ✅ **Lower operational overhead**: Simplified monitoring
- ✅ **Resource sharing**: Better utilization (idle capacity reused)
- ✅ **Faster onboarding**: New customer = new team (minutes, not hours)

**Cons:**
- ❌ **Noisy neighbor**: One customer's heavy usage affects others
- ❌ **Security concerns**: Customers share same database/infrastructure
- ❌ **Compliance challenges**: Some industries require dedicated infrastructure (banking, healthcare)
- ❌ **Limited customization**: All customers on same n8n version
- ❌ **Risk of misconfiguration**: Bug could expose customer A's data to customer B

**When to use:**
- Small/medium customers (SMB)
- Standard workflows (no special customization)
- Cost-sensitive customers
- Fast onboarding required
- Non-regulated industries

**Similar products:**
- Slack (multi-tenant SaaS)
- Zapier (multi-tenant SaaS)
- Notion (multi-tenant SaaS)

---

### Option B: Dedicated Instance Per Customer (Isolated)

**Architecture:**
```
┌────────────────────────────────────────────────────────┐
│         LightOn Cloud Infrastructure                   │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │  Customer A: Acme Corp                       │     │
│  │  • Dedicated n8n instance                    │     │
│  │  • Dedicated PostgreSQL database             │     │
│  │  • Dedicated Redis                           │     │
│  │  • URL: acme.n8n.lighton.cloud               │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │  Customer B: Widget Inc                      │     │
│  │  • Dedicated n8n instance                    │     │
│  │  • Dedicated PostgreSQL database             │     │
│  │  • Dedicated Redis                           │     │
│  │  • URL: widget.n8n.lighton.cloud             │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │  Customer C: Example LLC                     │     │
│  │  • Dedicated n8n instance                    │     │
│  │  • Dedicated PostgreSQL database             │     │
│  │  • Dedicated Redis                           │     │
│  │  • URL: example.n8n.lighton.cloud            │     │
│  └──────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────┘
```

**Deployment per customer:**
```yaml
# Kubernetes manifest
apiVersion: apps/v1
kind: Deployment
metadata:
  name: n8n-acme-corp
  namespace: customer-acme
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: n8n
        image: n8nio/n8n-enterprise:latest
        env:
        - name: DB_POSTGRESDB_HOST
          value: postgres-acme-corp.internal  # Dedicated DB
        - name: N8N_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: acme-corp-secrets
              key: encryption-key
---
apiVersion: v1
kind: Service
metadata:
  name: n8n-acme-corp
spec:
  type: LoadBalancer
  selector:
    app: n8n-acme-corp
```

**Pros:**
- ✅ **Complete isolation**: No shared resources between customers
- ✅ **Security**: Data breaches can't cross customer boundaries
- ✅ **Compliance**: Meets strict regulatory requirements (SOC2, HIPAA, PCI-DSS)
- ✅ **Performance**: No noisy neighbors
- ✅ **Customization**: Each customer can have different n8n version, config
- ✅ **Customer confidence**: "We have our own instance" sounds better

**Cons:**
- ❌ **High cost**: Each customer needs dedicated resources (even if idle)
- ❌ **Operational overhead**: Must manage N instances (updates, monitoring, backups)
- ❌ **Longer onboarding**: Provisioning takes 15-30 minutes
- ❌ **Resource waste**: Small customers pay for unused capacity
- ❌ **Scaling complexity**: Need to provision ahead of customer growth

**Cost breakdown (per customer):**
```
Monthly cost per customer:
• n8n instance (2 pods):          $200
• PostgreSQL (managed):            $150
• Redis (managed):                 $50
• Load balancer:                   $20
• Storage (100GB):                 $10
• Monitoring/logging:              $20
• Backups:                         $30
────────────────────────────────────────
Total per customer:                $480/month

Break-even: Need to charge >$500/month per customer
```

**When to use:**
- Enterprise customers (large companies)
- Regulated industries (finance, healthcare, government)
- Customers with compliance requirements
- Customers willing to pay premium
- High-security requirements

**Similar products:**
- GitHub Enterprise Server (dedicated instance option)
- Salesforce Private Cloud
- MongoDB Atlas Dedicated Cluster

---

### Option C: Hybrid - Pooled Infrastructure, Namespace Isolation (Recommended)

**Architecture:**
```
┌────────────────────────────────────────────────────────┐
│     LightOn Cloud (Shared Kubernetes Cluster)          │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │  Namespace: customer-acme                    │     │
│  │  • n8n pod(s)                                │     │
│  │  • PostgreSQL (shared infra, isolated DB)   │     │
│  │  • Redis (shared infra, isolated keyspace)  │     │
│  │  • Network policies (isolated traffic)      │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │  Namespace: customer-widget                  │     │
│  │  • n8n pod(s)                                │     │
│  │  • PostgreSQL (shared infra, isolated DB)   │     │
│  │  • Redis (shared infra, isolated keyspace)  │     │
│  │  • Network policies (isolated traffic)      │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  Shared Control Plane:                                │
│  • Kubernetes master                                  │
│  • Monitoring (Prometheus)                            │
│  • Logging (ELK)                                      │
│  • Load balancer                                      │
└────────────────────────────────────────────────────────┘
```

**How it works:**

1. **Kubernetes namespace per customer:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: customer-acme
  labels:
    customer: acme-corp
    tier: enterprise

---
# Network policy: Acme can't talk to Widget
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-cross-customer
  namespace: customer-acme
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          customer: acme-corp  # Only same customer
```

2. **Shared PostgreSQL, isolated databases:**
```sql
-- Shared PostgreSQL server, but separate databases
CREATE DATABASE n8n_acme_corp;
CREATE USER acme_user WITH PASSWORD '...';
GRANT ALL ON DATABASE n8n_acme_corp TO acme_user;

CREATE DATABASE n8n_widget_inc;
CREATE USER widget_user WITH PASSWORD '...';
GRANT ALL ON DATABASE n8n_widget_inc TO widget_user;

-- Users cannot access each other's databases
REVOKE ALL ON DATABASE n8n_widget_inc FROM acme_user;
```

3. **Resource quotas per namespace:**
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: acme-quota
  namespace: customer-acme
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    persistentvolumeclaims: "10"
```

**Pros:**
- ✅ **Good isolation**: Customers logically separated
- ✅ **Cost-efficient**: Share infrastructure, but customers independent
- ✅ **Performance**: Network policies prevent noisy neighbors
- ✅ **Compliance**: Can meet most requirements (namespaces = "soft multi-tenancy")
- ✅ **Flexibility**: Can move to dedicated if needed
- ✅ **Operational efficiency**: Easier to manage than full isolation

**Cons:**
- ❌ **Still shared infrastructure**: All customers on same K8s cluster
- ❌ **Moderate complexity**: More complex than Option A, simpler than Option B
- ❌ **Risk of cluster-level issues**: Kubernetes master failure affects all

**Cost breakdown:**
```
Shared costs (split across all customers):
• Kubernetes control plane:        $500/month
• Shared monitoring:               $200/month
• Shared networking:               $100/month
────────────────────────────────────────────
Total shared:                      $800/month

Per-customer costs:
• n8n pods (allocated resources):  $100/month
• Database (isolated):             $80/month
• Redis (isolated keyspace):       $30/month
────────────────────────────────────────────
Total per customer:                $210/month

With 10 customers:
• Shared costs / 10:               $80/month
• Per-customer costs:              $210/month
────────────────────────────────────────────
Cost per customer:                 $290/month

Break-even: Can charge $350-400/month and be profitable
```

**When to use:**
- Most enterprise customers
- Balance between cost and isolation
- Medium security requirements
- Growing customer base
- **This is the sweet spot for most SaaS providers**

**Similar products:**
- AWS RDS (multi-tenant infrastructure, isolated instances)
- MongoDB Atlas (shared clusters, isolated databases)
- Most modern SaaS platforms

---

## Comparison Matrix

| Factor | Option A: Shared | Option B: Dedicated | Option C: Hybrid |
|--------|------------------|---------------------|------------------|
| **Cost per customer** | $50-100/month | $480+/month | $290/month |
| **Isolation level** | Low (team-based) | High (full) | Medium (namespace) |
| **Onboarding time** | 1 minute | 30 minutes | 5 minutes |
| **Compliance** | Basic | Full (HIPAA, etc.) | Most (SOC2, ISO) |
| **Performance** | Variable (noisy neighbor) | Dedicated | Good (quotas) |
| **Operational overhead** | Low (1 instance) | High (N instances) | Medium (N namespaces) |
| **Customization** | Limited | Full | Moderate |
| **Noisy neighbor risk** | High | None | Low |
| **Best for** | SMB, cost-sensitive | Enterprise, regulated | Most customers |

---

## Recommended Approach for LightOn

### Phase 1: Start with Option C (Hybrid)

**Why:**
- Good balance of cost, isolation, and complexity
- Can serve both SMB and mid-market enterprise
- Easier to scale than Option B
- Better isolation than Option A

**Target customers:**
- 20-500 employees
- $5,000-50,000/month Paradigm contract
- Standard compliance (SOC2, ISO 27001)
- Willing to pay $500-1,000/month for n8n hosting

---

### Phase 2: Add Option B for Enterprise Tier

**When to offer dedicated:**
- Customer >1,000 employees
- Regulated industry (finance, healthcare, government)
- >$100,000/year Paradigm contract
- Strict compliance (HIPAA, PCI-DSS, FedRAMP)
- Willing to pay $2,000+/month for n8n hosting

**Pricing:**
- Hybrid (Option C): $500/month
- Dedicated (Option B): $2,000/month (4x price for 2x cost)

---

### Phase 3: Consider Option A for Freemium/Trial

**Use case:**
- Free trial (7-30 days)
- Freemium tier (limited workflows)
- Pilot projects
- Proof of concept

**Migration path:**
```
Trial (Option A) → Paid (Option C) → Enterprise (Option B)
    Free        →  $500/month     →   $2,000/month
```

---

## Implementation Checklist for LightOn

### For Customer-Owned n8n (Question 1):

- [ ] Create validation script (paradigm-n8n-validator.sh)
- [ ] Document dual SSO setup
- [ ] Create configuration templates
- [ ] Build health check workflow
- [ ] Write integration guide (per customer type)
- [ ] Create certification program
- [ ] Define support SLA requirements
- [ ] Test with 2-3 pilot customers

---

### For LightOn-Hosted n8n (Question 2):

**Phase 1: Hybrid Architecture (Option C)**

- [ ] Set up Kubernetes cluster
- [ ] Create namespace templates
- [ ] Configure network policies
- [ ] Set up shared PostgreSQL cluster
- [ ] Configure Redis multi-tenancy
- [ ] Implement resource quotas
- [ ] Build customer provisioning automation
- [ ] Set up monitoring per customer
- [ ] Test with 5-10 pilot customers

**Phase 2: Add Dedicated Tier (Option B)**

- [ ] Create Terraform/Helm charts for dedicated deployments
- [ ] Document when to recommend dedicated
- [ ] Build cost calculator tool
- [ ] Update sales playbook
- [ ] Test with 1-2 enterprise customers

**Phase 3: Operations**

- [ ] Implement automated backups (per customer)
- [ ] Set up alerting (per customer)
- [ ] Create customer dashboard (usage metrics)
- [ ] Build self-service portal (customer can see quotas, logs)
- [ ] Document runbooks (incident response, scaling, etc.)

---

## Decision Framework

### For Customer (Deciding on deployment model):

```
Do you already have n8n?
├─ Yes → Keep it, add Paradigm nodes (Question 1)
│  ├─ Have n8n Enterprise? → Dual SSO (Option 1)
│  ├─ Don't have Enterprise? → Manual credentials (Option 3)
│  └─ Want complete isolation? → Separate instance (Option 2)
│
└─ No → LightOn hosts n8n (Question 2)
   ├─ SMB (<100 users) → Hybrid tier - $500/month (Option C)
   ├─ Mid-market (100-1000) → Hybrid tier - $500/month (Option C)
   └─ Enterprise (>1000) OR regulated → Dedicated tier - $2,000/month (Option B)
```

### For LightOn (Choosing hosting model):

```
Customer size and requirements:
├─ Trial/POC → Shared multi-tenant (Option A) - Free/minimal cost
├─ SMB/Mid-market → Hybrid namespace isolation (Option C) - $290 cost, charge $500
└─ Enterprise/Regulated → Dedicated instance (Option B) - $480 cost, charge $2,000
```

---

## Conclusion

**Question 1: Customer has own n8n**
- ✅ **Recommended: Dual SSO** (Option 1) - Add Paradigm SSO alongside existing
- ✅ Enforce via: validation scripts, documentation, training, support SLA
- ✅ LightOn provides: nodes, config templates, health checks, certification

**Question 2: LightOn hosts n8n**
- ✅ **Recommended: Hybrid (Option C)** for most customers
  - Kubernetes namespaces
  - Isolated databases on shared infrastructure
  - $290 cost per customer, charge $500/month
  - Good balance of isolation, cost, compliance
- ✅ **Offer Dedicated (Option B)** for enterprise tier
  - Fully isolated instance per customer
  - $480 cost per customer, charge $2,000/month
  - For regulated industries, large enterprises
- ✅ **Use Shared (Option A)** for trial/freemium only
  - Single multi-tenant instance
  - Lowest cost, quickest onboarding
  - Graduate to paid hybrid tier

**Best practice:** Start with Hybrid (Option C), add Dedicated tier as you grow.
