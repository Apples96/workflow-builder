# n8n Implementation Guide for Paradigm API Workflows

## Executive Summary

This guide outlines the requirements, architecture, and implementation plan for deploying n8n as a production workflow automation platform for customers using the Paradigm API.

---

## 1. What the Customer Gets

### Before (Current Workflow Builder):
- User writes natural language description
- System generates and executes Python code
- One-time execution, manual re-runs
- Results shown in web interface

### After (n8n):
- User builds workflow visually (drag-and-drop)
- Workflows saved as reusable templates
- Scheduled execution (hourly, daily, on-trigger)
- Monitoring dashboard with execution history
- Error alerts via email/Slack
- Team collaboration (multiple users can edit workflows)
- Version control (workflow history)

---

## 2. On-Premise Deployment Architecture

### Infrastructure Requirements

#### Minimum Hardware (Small deployment):
- **CPU**: 4 cores
- **RAM**: 8 GB
- **Storage**: 50 GB SSD
- **OS**: Ubuntu 22.04 LTS / RHEL 8+ / Docker-compatible

#### Recommended (Production):
- **CPU**: 8 cores
- **RAM**: 16 GB
- **Storage**: 200 GB SSD (for logs, temp files, execution history)
- **Database**: PostgreSQL 14+ (for workflow persistence)

### Network Requirements:
- **Outbound HTTPS** to Paradigm API (paradigm.lighton.ai)
- **Outbound HTTPS** to Claude API (api.anthropic.com) - if using AI features
- **Internal network** access for users (port 5678 by default)
- **Optional**: Reverse proxy (nginx) for HTTPS/SSL

---

## 3. Deployment Options

### Option A: Docker Compose (Recommended for most on-prem)

**What gets deployed:**
```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n
      - DB_POSTGRESDB_PASSWORD=${POSTGRES_PASSWORD}
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - LIGHTON_API_KEY=${LIGHTON_API_KEY}
    volumes:
      - n8n_data:/home/node/.n8n
      - ./custom-nodes:/home/node/.n8n/custom
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:14
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  n8n_data:
  postgres_data:
```

**Deployment time**: 1-2 hours (including testing)

---

### Option B: Kubernetes (For enterprise/large scale)

**What gets deployed:**
- n8n deployment (2+ replicas for HA)
- PostgreSQL StatefulSet
- Redis (for queue management)
- Ingress controller (for HTTPS)
- Persistent volumes for data

**Deployment time**: 1-2 days (including cluster setup if needed)

---

## 4. Custom Paradigm API Nodes

### What Needs to Be Built

We need to create 11 custom n8n community nodes (one per Paradigm endpoint):

#### Node 1: Paradigm Document Search
**Configuration UI:**
```
┌─────────────────────────────────────┐
│ Paradigm Document Search            │
├─────────────────────────────────────┤
│ API Credentials: [Select credential]│
│                                     │
│ Search Query: [text input]         │
│ File IDs: [list of numbers]        │
│ Max Results: [5]                    │
│ Collection: [private/company/ws]    │
└─────────────────────────────────────┘
```

**Output:**
```json
{
  "results": [...],
  "total_results": 5,
  "query": "buyer information"
}
```

#### Node 2: Paradigm Analyze Documents
**Configuration UI:**
```
┌─────────────────────────────────────┐
│ Paradigm Analyze Documents          │
├─────────────────────────────────────┤
│ API Credentials: [Select credential]│
│                                     │
│ Analysis Query: [text input]       │
│ Document IDs: [list of numbers]    │
│ Wait for Result: [✓] Yes           │
│ Timeout (seconds): [300]           │
└─────────────────────────────────────┘
```

#### Node 3: Paradigm Chat Completion (with Guided Output)
**Configuration UI:**
```
┌─────────────────────────────────────┐
│ Paradigm Chat Completion            │
├─────────────────────────────────────┤
│ API Credentials: [Select credential]│
│                                     │
│ Prompt: [text area]                │
│                                     │
│ Output Type:                        │
│  ○ Free text                        │
│  ● Guided JSON                      │
│  ○ Guided Regex                     │
│  ○ Guided Choice                    │
│                                     │
│ JSON Schema: [JSON editor]          │
│ {                                   │
│   "type": "object",                 │
│   "properties": {                   │
│     "buyer_name": {"type": "string"}│
│   }                                 │
│ }                                   │
└─────────────────────────────────────┘
```

#### Node 4: Paradigm Upload File
#### Node 5: Paradigm Get File
#### Node 6: Paradigm Delete File
#### Node 7: Paradigm Wait for Embedding
#### Node 8: Paradigm Get File Chunks
#### Node 9: Paradigm Filter Chunks
#### Node 10: Paradigm Query (no synthesis)
#### Node 11: Paradigm Analyze Image

### Development Effort

**Per node:**
- TypeScript development: 4-8 hours
- Testing: 2-4 hours
- Documentation: 1-2 hours

**Total: 77-154 hours (2-4 weeks for one developer)**

---

## 5. Customer Onboarding Process

### Week 1: Infrastructure Setup

**Day 1-2: Server Provisioning**
- Customer provisions VM/server with required specs
- Install Docker + Docker Compose
- Set up PostgreSQL database
- Configure network access and firewall rules

**Day 3-4: n8n Deployment**
```bash
# Clone deployment repo
git clone https://github.com/your-org/n8n-paradigm-deployment.git
cd n8n-paradigm-deployment

# Configure environment
cp .env.example .env
nano .env  # Add Paradigm API key, database passwords

# Deploy
docker-compose up -d

# Verify
curl http://localhost:5678
```

**Day 5: SSL/Reverse Proxy Setup**
```nginx
# /etc/nginx/sites-available/n8n
server {
    listen 443 ssl;
    server_name workflows.customer.com;

    ssl_certificate /etc/ssl/certs/customer.crt;
    ssl_certificate_key /etc/ssl/private/customer.key;

    location / {
        proxy_pass http://localhost:5678;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

### Week 2: Custom Nodes Installation

**Install Paradigm nodes:**
```bash
# Inside n8n container
cd /home/node/.n8n/custom
npm install n8n-nodes-paradigm-api

# Or mount as volume
docker-compose down
# Add to docker-compose.yml:
#   volumes:
#     - ./paradigm-nodes:/home/node/.n8n/custom
docker-compose up -d
```

**Configure Paradigm credentials in n8n UI:**
1. Go to Settings → Credentials
2. Add "Paradigm API" credential
3. Enter API key and base URL
4. Test connection

---

### Week 3: User Training

**Session 1: n8n Basics (2 hours)**
- Interface overview
- Creating first workflow
- Triggers, nodes, connections
- Testing and debugging

**Session 2: Paradigm Nodes (2 hours)**
- Overview of all 11 nodes
- File upload and management
- Document search and analysis
- Structured data extraction

**Session 3: Production Workflows (2 hours)**
- Error handling strategies
- Retry logic
- Scheduling workflows
- Monitoring and alerts

---

### Week 4: Migration and Go-Live

**Migrate existing workflows:**
1. Identify top 5-10 most-used workflows from current builder
2. Rebuild visually in n8n
3. Side-by-side testing (old vs new)
4. Documentation for each workflow

**Go-live checklist:**
- [ ] All workflows tested
- [ ] Users trained
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Support documentation ready
- [ ] Rollback plan documented

---

## 6. Example: Real Production Workflow

### Scenario: Daily Contract Analysis

**Business requirement:**
"Every morning at 8am, analyze all contracts uploaded yesterday, extract key terms (buyer, seller, amount, dates), flag any non-standard clauses, and send a summary report via email."

### n8n Workflow:

```
[Trigger: Cron - Daily 8am]
     ↓
[Get Yesterday's Files]
(Custom code: list files uploaded in last 24h)
     ↓
[Loop: For Each File]
     ↓
[Paradigm: Wait for Embedding]
(Ensure file is indexed)
     ↓
[Paradigm: Chat Completion]
(guided_json: contract schema)
     ↓
[Check for Non-Standard Clauses]
(IF node: check for specific patterns)
     ↓
[Flag if needed] ──┐
     ↓             │
[Store Results] ←──┘
     ↓
[Aggregate All Results]
     ↓
[Generate HTML Report]
     ↓
[Send Email]
(To: legal-team@customer.com)
```

**Configuration saved as JSON:**
```json
{
  "name": "Daily Contract Analysis",
  "nodes": [
    {
      "type": "n8n-nodes-base.cron",
      "parameters": {
        "triggerTimes": {
          "item": [{"hour": 8, "minute": 0}]
        }
      }
    },
    {
      "type": "n8n-nodes-paradigm.chatCompletion",
      "parameters": {
        "prompt": "Extract key contract terms",
        "guidedJson": {
          "type": "object",
          "properties": {
            "buyer": {"type": "string"},
            "seller": {"type": "string"},
            "amount": {"type": "number"},
            "date": {"type": "string"}
          }
        }
      }
    }
  ]
}
```

---

## 7. Ongoing Operations

### Daily Operations:
- Monitor workflow executions via n8n dashboard
- Check error alerts (email/Slack)
- Review execution logs for failed workflows

### Weekly:
- Review workflow performance metrics
- Optimize slow workflows
- Update documentation

### Monthly:
- Update n8n to latest version
- Review and archive old execution history
- Database maintenance (vacuum, reindex)

### Backups:
```bash
# Automated daily backup script
#!/bin/bash
BACKUP_DIR=/backups/n8n
DATE=$(date +%Y%m%d)

# Backup database
docker exec n8n-postgres pg_dump -U n8n n8n > $BACKUP_DIR/n8n-db-$DATE.sql

# Backup workflow files
docker exec n8n tar czf - /home/node/.n8n > $BACKUP_DIR/n8n-data-$DATE.tar.gz

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

---

## 8. Cost Analysis

### One-Time Costs:

| Item | Cost (Internal) | Cost (External Consultant) |
|------|----------------|---------------------------|
| Infrastructure setup | 1 day (IT) | €800 |
| n8n deployment | 1 day (DevOps) | €1,200 |
| Custom node development | 2-4 weeks (Dev) | €8,000-€16,000 |
| Training materials | 1 week (Dev) | €2,000 |
| User training | 3 sessions | €1,500 |
| **TOTAL** | **~5-7 weeks internal** | **€13,500-€21,500** |

### Ongoing Costs:

| Item | Annual Cost |
|------|------------|
| Server hosting (on-prem) | €0 (existing infrastructure) |
| n8n license | €0 (self-hosted open source) |
| Maintenance (updates) | 1 day/month = €6,000/year |
| **TOTAL** | **€6,000/year** |

---

## 9. Comparison: Current Builder vs n8n

| Feature | Current Builder | n8n |
|---------|----------------|-----|
| **Ease of use** | Natural language (easiest) | Visual (easy) |
| **Learning curve** | 5 minutes | 2-3 hours |
| **Workflow reusability** | None (one-time) | Full (saved templates) |
| **Scheduling** | Manual only | Cron, webhooks, triggers |
| **Monitoring** | None | Built-in dashboard |
| **Error handling** | Limited retry | Full retry + alerting |
| **Team collaboration** | No | Yes (multi-user) |
| **Version control** | No | Yes (workflow history) |
| **Integration ecosystem** | Paradigm only | 400+ integrations |
| **Debugging** | Text logs | Visual execution view |
| **Production readiness** | Prototype | Production-grade |
| **Deployment effort** | Already deployed | 4-6 weeks |

---

## 10. Decision Framework

### Use Current Workflow Builder when:
- ✅ One-off, experimental workflows
- ✅ Rapid prototyping
- ✅ User just wants to describe and run
- ✅ No scheduling needed
- ✅ Single user operation

### Use n8n when:
- ✅ Production, recurring workflows
- ✅ Team needs to collaborate on workflows
- ✅ Scheduled execution required
- ✅ Need monitoring and alerts
- ✅ Integration with other systems (email, databases, etc.)
- ✅ Workflow versioning and audit trail needed

---

## 11. Hybrid Architecture (Recommended)

```
┌─────────────────────────────────────────────┐
│         Customer Environment                │
│                                             │
│  ┌──────────────────┐  ┌─────────────────┐ │
│  │  Workflow Builder│  │      n8n        │ │
│  │  (Prototyping)   │  │  (Production)   │ │
│  │                  │  │                 │ │
│  │ - Natural lang   │  │ - Scheduled     │ │
│  │ - Quick tests    │  │ - Monitored     │ │
│  │ - R&D            │  │ - Team collab   │ │
│  └────────┬─────────┘  └────────┬────────┘ │
│           │                     │          │
│           └──────────┬──────────┘          │
│                      ↓                     │
│         ┌─────────────────────────┐        │
│         │   Paradigm API Nodes    │        │
│         │  (Shared Components)    │        │
│         └─────────────────────────┘        │
│                      ↓                     │
│         ┌─────────────────────────┐        │
│         │   Paradigm API          │        │
│         │  (paradigm.lighton.ai)  │        │
│         └─────────────────────────┘        │
└─────────────────────────────────────────────┘
```

**Best of both worlds:**
- Users prototype with natural language builder
- Once validated, rebuild in n8n for production
- Both use same Paradigm API integration

---

## 12. Implementation Roadmap

### Phase 1: Preparation (Week 1-2)
- [ ] Hardware/VM provisioning
- [ ] Network/firewall configuration
- [ ] Install Docker + PostgreSQL
- [ ] Deploy n8n instance
- [ ] SSL certificate setup

### Phase 2: Development (Week 3-6)
- [ ] Develop 11 Paradigm custom nodes
- [ ] Unit testing for each node
- [ ] Integration testing
- [ ] Documentation

### Phase 3: Integration (Week 7-8)
- [ ] Install custom nodes in n8n
- [ ] Configure Paradigm credentials
- [ ] Migrate top 5 workflows
- [ ] Side-by-side testing

### Phase 4: Training (Week 9-10)
- [ ] Train admin users (2 days)
- [ ] Train end users (3 days)
- [ ] Create internal documentation
- [ ] Record video tutorials

### Phase 5: Go-Live (Week 11-12)
- [ ] Final testing
- [ ] Backup strategy implemented
- [ ] Monitoring configured
- [ ] Support handoff
- [ ] Launch

**Total timeline: 12 weeks (3 months)**

---

## 13. Risk Mitigation

### Risk 1: Node Development Delays
**Mitigation:**
- Start with top 5 most-used Paradigm endpoints
- Roll out incrementally

### Risk 2: User Adoption
**Mitigation:**
- Comprehensive training
- Video tutorials
- Internal champions
- Keep current builder available during transition

### Risk 3: Performance Issues
**Mitigation:**
- Load testing before go-live
- Horizontal scaling (add more n8n workers)
- Database optimization

### Risk 4: Integration Bugs
**Mitigation:**
- Extensive testing period (2 weeks)
- Side-by-side validation
- Phased rollout

---

## 14. Success Metrics

Track these KPIs after deployment:

- **Workflow execution success rate** (target: >95%)
- **Average workflow creation time** (compare before/after)
- **Number of scheduled workflows** (production adoption)
- **User satisfaction score** (survey after 1 month)
- **Time saved vs manual processes** (hours/week)
- **Support tickets related to workflows** (should decrease)

---

## Conclusion

For an on-premise customer not yet using n8n, the implementation requires:

**Upfront investment:**
- 12 weeks (3 months) implementation
- €13,500-€21,500 (if outsourced) or 5-7 weeks internal dev time
- Training and change management

**Ongoing:**
- €6,000/year maintenance
- Better workflow reliability and monitoring
- Team collaboration capabilities
- 400+ additional integration options

**Recommendation:** Implement n8n for production workflows while keeping the current Workflow Builder for rapid prototyping and experimentation. This hybrid approach maximizes value while minimizing risk.
