# LightOn Workflow Builder

Application de génération et d'exécution de workflows automatisés utilisant l'API Anthropic Claude et l'API LightOn Paradigm.

## 🚀 Démarrage Rapide avec Docker

```bash
# 1. Cloner le repository
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-

# 2. Configurer les clés API
cp .env.example .env
# Éditer .env et ajouter vos clés :
# ANTHROPIC_API_KEY=votre_clé_anthropic
# LIGHTON_API_KEY=votre_clé_lighton

# 3. Démarrer avec Docker Compose
docker-compose up --build

# 4. Accéder à l'application
# Frontend : http://localhost:3000
# API Backend : http://localhost:8000/docs
```

**✅ Avantages Docker** :
- Configuration minimale
- Environnement isolé et reproductible
- Prêt pour production (déployable sur n'importe quel serveur avec Docker)
- Pas de limite de functions serverless

## 🔧 Autres Options de Déploiement

### Option Vercel (Requires Pro Plan)

⚠️ **Attention** : Le workflow builder nécessite Vercel Pro ($20/mois) pour fonctionner correctement.

**Pourquoi Pro est requis** :
- **Python Runtime** : Le workflow builder utilise Python/FastAPI (pas disponible en free tier)
- **Execution Time** : La génération de workflows peut prendre 30-60s+ (free tier limité à 10s)
- **Function Count** : Le builder utilise plusieurs endpoints API (limite atteinte rapidement en free tier)

**Déploiement Vercel** :
1. Connectez votre repo GitHub/GitLab à Vercel
2. Ajoutez les variables d'environnement dans Vercel :
   - `ANTHROPIC_API_KEY`
   - `LIGHTON_API_KEY`
3. Liez Vercel KV (Storage) :
   - Les variables `KV_REST_API_URL` et `KV_REST_API_TOKEN` sont créées automatiquement
   - Le code détecte et utilise ces variables automatiquement
4. Déployez : `git push` (automatique)

**Note** : Le code supporte automatiquement les deux conventions :
- Variables Vercel KV (créées automatiquement lors du linking)
- Variables Upstash directes (configuration manuelle)

### Option Python Manuel

Déployer sur votre propre infrastructure (VPS, cloud VM, serveur on-premises).

```bash
# 1. Cloner et installer
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-
pip install -r requirements.txt

# 2. Configurer les variables d'environnement
cp .env.example .env
nano .env  # Ajouter ANTHROPIC_API_KEY et LIGHTON_API_KEY

# 3. Démarrer le serveur
python -m uvicorn api.index:app --host 0.0.0.0 --port 8000

# Ou avec plus d'options de production
uvicorn api.index:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

**Configuration Nginx (optionnel)** :
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## 📋 Prérequis

1. **Docker Desktop** installé (pour démarrage rapide)
2. **Clés API** :
   - Anthropic API key (pour la génération de workflows)
   - LightOn Paradigm API key (pour l'exécution des workflows)

## ✨ Fonctionnalités Principales

### 1. Génération de Workflows par IA

- **Natural Language to Code**: Décrivez vos workflows en langage naturel, Claude Sonnet 4 génère le code Python exécutable
- **Enhancement Description**: Amélioration automatique des descriptions utilisateur avant génération
- **Auto-Validation avec Retry**: Jusqu'à 3 tentatives avec feedback d'erreur contextuel pour auto-correction
- **Post-Processing Intelligent**: Correction automatique des erreurs de syntaxe f-strings
- **Détection de Complexité**: Identification automatique de workflows complexes (>40 appels API) avec gestion de rate limiting
- **Optimisation des Performances**: Parallelisation automatique via asyncio.gather() pour les opérations indépendantes

### 2. Intégration Complète Paradigm API

**Recherche et Analyse de Documents:**
- `document_search()` - Recherche sémantique dans vos documents
- `search_with_vision_fallback()` - Fallback automatique vers VisionDocumentSearch pour documents scannés
- `analyze_documents_with_polling()` - Analyse approfondie avec récupération automatique des résultats
- `chat_completion()` - Complétion IA avec extraction de données structurées :
  - **guided_choice**: Sélection forcée parmi liste prédéfinie (classification)
  - **guided_regex**: Format garanti (SIRET, IBAN, téléphones, dates, montants)
  - **guided_json**: Extraction JSON structurée

**Gestion de Fichiers:**
- `upload_file()` - Upload vers Paradigm avec indexation automatique
- `wait_for_embedding()` - Attente automatique de l'indexation (timeout 5min)
- `get_file()` / `delete_file()` - Gestion complète du cycle de vie
- `get_file_chunks()` - Récupération des chunks de documents

**APIs Avancées:**
- `filter_chunks()` - Filtrage par pertinence (+20% précision)
- `query()` - Extraction de chunks sans synthèse AI (30% plus rapide)
- `analyze_image()` - Analyse d'images avec IA

**Performance:**
- Session HTTP réutilisable (5.55x plus rapide)
- Support complet des opérations async

### 3. Exécution Sécurisée

- **Sandboxing**: Environnement d'exécution restreint avec built-ins sécurisés uniquement
- **Timeout Configurable**: Protection contre les exécutions infinies (défaut 30 min)
- **File Attachments**: Support natif de fichiers joints via `attached_file_ids`
- **Injection Sécurisée**: Clés API injectées automatiquement à l'exécution
- **Logging Complet**: Capture stdout/stderr avec traçage API détaillé
- **Support Async**: Workflows synchrones et asynchrones

### 4. Persistance et Stockage

- **Upstash Redis**: Stockage serverless-compatible (TTL 24h)
- **Vercel KV**: Détection et utilisation automatique des variables Vercel
- **Fallback In-Memory**: Fonctionnement sans Redis si nécessaire
- **Workflow History**: Stockage des exécutions et résultats

### 5. Export et Packages

**Workflow Runner (Package Standalone):**
- Interface web dynamique générée automatiquement par analyse du code
- Détection intelligente des champs (inputs texte, uploads fichiers, types multiples)
- Backend FastAPI complet avec client Paradigm
- Documentation bilingue (FR/EN)
- Configuration Docker prête à l'emploi
- Export PDF intégré (jsPDF)
- ⚠️ Local dev uniquement (limite serverless Vercel)

**MCP Server Package:**
- Serveur MCP dual-mode (stdio pour Claude Desktop + HTTP pour Paradigm)
- Support multi-formats d'entrée (paths locaux, file IDs, auto-upload)
- Attente automatique d'indexation (wait_for_embedding 5min)
- Configuration Docker + bearer token auth
- ⚠️ Limitations: 4min timeout Claude Desktop, bug file_ids Paradigm

### 6. Rapports PDF Professionnels

- Génération automatique de rapports vendor-neutral
- Support Markdown (headers, listes, tables, bold/italic)
- Affichage structuré des données JSON
- Métadonnées complètes (nom, description, durée, status)
- Typographie professionnelle (ReportLab)

### 7. Interface Web Moderne

- **Vanilla JavaScript**: Sans dépendances framework
- **Upload Drag-and-Drop**: Interface visuelle de fichiers
- **Monitoring en Temps Réel**: Logs colorés avec traçage API complet
- **Code Preview**: Visualisation du workflow généré
- **Téléchargements**: PDF, Workflow Runner Package, MCP Package
- **Responsive**: Compatible desktop et mobile


## 📖 API Endpoints

### Workflows
- `POST /api/workflows` - Créer un workflow depuis une description
- `POST /api/workflows/enhance-description` - Améliorer une description avec l'IA
- `GET /api/workflows/{id}` - Récupérer les détails d'un workflow
- `POST /api/workflows/{id}/execute` - Exécuter un workflow
- `GET /api/workflows/{id}/executions/{exec_id}` - Détails d'exécution
- `GET /api/workflows/{id}/executions/{exec_id}/pdf` - Télécharger rapport PDF
- `POST /api/workflows-with-files` - Créer un workflow avec accès à des fichiers spécifiques

### Packages (Local uniquement)
- `POST /api/workflow/generate-package/{id}` - Générer Workflow Runner Package (ZIP)
- `POST /api/workflow/generate-mcp-package/{id}` - Générer MCP Server Package (ZIP)

### Files
- `POST /api/files/upload` - Uploader un fichier vers Paradigm
- `GET /api/files/{id}` - Info sur un fichier (status, taille, etc.)
- `DELETE /api/files/{id}` - Supprimer un fichier

### Health
- `GET /health` - Health check pour monitoring
- `GET /` - Interface web (frontend)

### Usage Example

```bash
# 1. Créer un workflow
curl -X POST "http://localhost:8000/api/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Analyser les CV uploadés et les comparer à une fiche de poste",
    "name": "Analyse de CV"
  }'

# 2. Uploader des fichiers
curl -X POST "http://localhost:8000/api/files/upload" \
  -F "file=@cv1.pdf" \
  -F "collection_type=private"

# 3. Exécuter le workflow avec fichiers attachés
curl -X POST "http://localhost:8000/api/workflows/{workflow_id}/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "Analyser les CV",
    "attached_file_ids": [123, 124, 125]
  }'
```

## Example Workflow

The system is designed to handle workflows like the example provided:

**Description**: "User inputs a long prompt with multiple sentences. For each sentence, perform a search using the Paradigm Docsearch tool. Return results formatted as 'Question: [sentence]' followed by 'Answer: [result]'."

**Sample Input**: "What is machine learning? How does artificial intelligence work? What are the benefits of cloud computing?"

**Expected Output**:
```
Question: What is machine learning?
Answer: [Search result about machine learning]

Question: How does artificial intelligence work?
Answer: [Search result about AI]

Question: What are the benefits of cloud computing?
Answer: [Search result about cloud computing benefits]
```

## 🔧 APIs Disponibles dans les Workflows Générés

Les workflows générés ont accès à un **ParadigmClient complet** avec toutes les APIs LightOn Paradigm :

### Recherche et Analyse de Documents
- `document_search(query, file_ids=...)` - Recherche sémantique dans vos documents
- `search_with_vision_fallback(query, file_ids)` - Recherche avec OCR automatique pour documents scannés
- `analyze_documents_with_polling(query, document_ids)` - Analyse approfondie avec récupération auto des résultats
- `chat_completion(prompt, guided_choice=..., guided_regex=..., guided_json=...)` - Complétion avec extraction structurée
  - **guided_choice** : Sélection forcée parmi liste prédéfinie (classification)
  - **guided_regex** : Format garanti (SIRET, IBAN, téléphone, dates, montants)
  - **guided_json** : Extraction JSON structurée avec schéma

### Gestion de Fichiers
- `upload_file(file_content, filename, collection_type=...)` - Upload vers Paradigm avec indexation auto
- `wait_for_embedding(file_id, timeout=300)` - Attente auto de l'indexation (timeout 5min)
- `get_file(file_id)` / `delete_file(file_id)` - Gestion complète du cycle de vie
- `get_file_chunks(file_id)` - Récupération des chunks de documents

### APIs Avancées
- `filter_chunks(query, chunk_ids, n=...)` - Filtrage par pertinence (+20% précision)
- `query(query, collection=...)` - Extraction de chunks sans synthèse AI (30% plus rapide)
- `analyze_image(image_path_or_url, prompt)` - Analyse d'images avec IA

### Extraction de Données Structurées

Les workflows peuvent extraire des données avec **garantie de format** :

```python
# Extraction de SIRET avec format garanti (14 chiffres)
siret = await paradigm_client.chat_completion(
    prompt="Extrais le numéro SIRET du document",
    guided_regex=r"\d{14}"
)

# Classification stricte parmi choix prédéfinis
status = await paradigm_client.chat_completion(
    prompt="Le document est-il conforme aux exigences ?",
    guided_choice=["conforme", "non_conforme", "incomplet"]
)

# Extraction JSON structurée
invoice_data = await paradigm_client.chat_completion(
    prompt="Extrais les données de la facture",
    guided_json={
        "type": "object",
        "properties": {
            "numero": {"type": "string"},
            "montant": {"type": "number"},
            "date": {"type": "string"}
        }
    }
)
```

**Patterns regex prédéfinis inclus** : SIRET (14 chiffres), SIREN (9 chiffres), IBAN, téléphone FR, dates ISO, montants EUR, emails.

### Performance
- Session HTTP réutilisable pour toutes les méthodes (5.55x plus rapide)
- Support complet des opérations async/await

## 📦 Workflow Runner - Package Standalone

Le **Workflow Runner** permet d'exporter un workflow complet sous forme de package ZIP autonome, prêt à être déployé chez un client.

### Génération d'un Package

**En mode développement local uniquement** (endpoint désactivé sur Vercel) :

```bash
# Via l'API
curl -X POST "http://localhost:8000/api/workflow/generate-package/{workflow_id}" \
  --output workflow-package.zip

# Via l'interface web
# Cliquer sur "Download Workflow Package" après création du workflow
```

### Contenu du Package

Le ZIP généré contient une **application complète et autonome** :

```
workflow-{name}-{id}.zip
├── frontend/
│   ├── index.html              # Interface dynamique auto-générée
│   ├── config.json             # Configuration UI (champs, types, etc.)
│   └── styles intégrés         # CSS responsive
├── backend/
│   ├── main.py                 # Serveur FastAPI
│   ├── workflow_code.py        # Code du workflow généré
│   ├── paradigm_client.py      # Client Paradigm complet
│   └── requirements.txt        # Dépendances Python
├── docker-compose.yml          # Configuration Docker
├── Dockerfile                  # Image Docker optimisée
├── README.md (FR)              # Documentation française
├── README_EN.md                # Documentation anglaise
└── .env.example                # Template de configuration
```

### Caractéristiques

- ✅ **UI Dynamique** : Interface générée automatiquement par analyse Claude du code
- ✅ **Bilingue** : Documentation complète FR + EN
- ✅ **Docker Ready** : `docker-compose up` et c'est prêt
- ✅ **PDF Export** : Génération de rapports intégrée
- ✅ **Standalone** : Aucune dépendance au système principal
- ✅ **Production Ready** : Configuration Uvicorn optimisée

### Déploiement Client

```bash
# 1. Extraire le ZIP
unzip workflow-package.zip
cd workflow-{name}-{id}

# 2. Configurer les clés API
cp .env.example .env
nano .env  # Ajouter LIGHTON_API_KEY et ANTHROPIC_API_KEY

# 3. Lancer avec Docker
docker-compose up -d

# 4. Accéder à l'interface
# http://localhost:8080
```

### Note Importante

⚠️ La génération de packages est **désactivée sur Vercel** pour rester dans la limite de 12 serverless functions. Utilisez le mode développement local pour générer des packages.

## 🔌 MCP Server Package - Intégration Claude Desktop

Le **MCP (Model Context Protocol) Package** permet d'intégrer vos workflows directement dans Claude Desktop ou Paradigm via le protocole MCP d'Anthropic.

### Génération d'un Package MCP

**En mode développement local uniquement** :

```bash
# Via l'interface web
# Cliquer sur "Download MCP Package" après création du workflow
```

### Contenu du Package MCP

```
mcp-workflow-{name}.zip
├── server.py                   # Serveur MCP (stdio + HTTP)
├── workflow.py                 # Code du workflow généré
├── paradigm_client.py          # Client Paradigm complet
├── requirements.txt            # Dépendances Python
├── docker-compose.yml          # Configuration Docker
├── Dockerfile                  # Image Docker
├── .env.example                # Template de configuration
└── README.md                   # Documentation complète
```

### Utilisation avec Claude Desktop

```bash
# 1. Extraire le package
unzip mcp-workflow-{name}.zip
cd mcp-workflow-{name}

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer Claude Desktop
# Éditer %APPDATA%\Claude\claude_desktop_config.json (Windows)
# ou ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
```

Ajouter cette configuration :

```json
{
  "mcpServers": {
    "your-workflow-name": {
      "command": "python",
      "args": ["C:\\path\\to\\mcp-workflow\\server.py"],
      "cwd": "C:\\path\\to\\mcp-workflow",
      "env": {
        "PARADIGM_API_KEY": "your_paradigm_api_key",
        "PARADIGM_BASE_URL": "https://paradigm.lighton.ai"
      }
    }
  }
}
```

**4. Redémarrer Claude Desktop** - Le workflow est maintenant disponible comme outil !

### Utilisation avec Paradigm (HTTP Mode)

Pour déployer le serveur MCP et l'utiliser avec Paradigm :

```bash
# 1. Déployer sur un serveur avec URL publique
docker-compose up -d

# 2. Dans Paradigm Admin → MCP Servers
# Ajouter : https://votre-serveur.com/mcp
# Bearer Token : optionnel (configuré dans .env)
```

⚠️ **Bug Connu Paradigm** : Les `file_ids` uploadés via l'interface Paradigm ne sont pas correctement transmis aux workflows MCP. Workaround : utilisez Claude Desktop en local jusqu'à correction du bug.

### Limitations

- **Claude Desktop** : Timeout de 4 minutes maximum par requête MCP
  - Limiter à 3-5 documents par requête
  - Pour workflows complexes, préférer le Workflow Runner Package standard
- **Paradigm HTTP** : Bug de transmission des file_ids (en cours de correction)

## 🧪 Tests

```bash
# Tests unitaires
pytest tests/

# Tests d'intégration
pytest tests/test_integration.py

# Test Docker
docker-compose up --build
```

## 📁 Structure du Projet

```
├── api/                          # Backend FastAPI
│   ├── index.py                 # Point d'entrée
│   ├── main.py                  # Application FastAPI principale
│   ├── config.py                # Configuration et variables d'env
│   ├── models.py                # Modèles Pydantic (requêtes/réponses)
│   ├── api_clients.py           # Clients HTTP Anthropic + Paradigm
│   ├── pdf_generator.py         # Génération de rapports PDF
│   └── workflow/                # Module de workflows
│       ├── generator.py         # Génération de code par IA
│       ├── executor.py          # Exécution sécurisée
│       ├── models.py            # Modèles de workflows
│       ├── package_generator.py # Génération de packages ZIP
│       └── workflow_analyzer.py # Analyse de workflows
├── tests/                       # Tests unitaires et d'intégration
├── index.html                   # Frontend (interface web)
├── requirements.txt             # Dépendances Python
├── .env                         # Variables d'environnement (NE PAS commiter!)
├── docker-compose.yml           # Configuration Docker
├── Dockerfile                   # Image Docker
└── vercel.json                  # Configuration Vercel
```

## 📚 Documentation

- **API Backend** : http://localhost:8000/docs (quand le serveur tourne)
- **Docker** : Voir [DOCKER_README.md](DOCKER_README.md)
- **API Paradigm** : https://paradigm.lighton.ai/docs

## 🔒 Sécurité

- **Sandboxed Execution**: Le code s'exécute dans un environnement restreint
- **Timeout Protection**: Les exécutions sont limitées dans le temps
- **Input Validation**: Toutes les entrées sont validées
- **Error Handling**: Gestion complète des erreurs et logging

## 🐛 Dépannage

**Problème : "Port already in use"**
- Arrêtez les conteneurs Docker : `docker-compose down`
- Vérifiez les processus sur les ports : `netstat -ano | findstr :8000`
- Si besoin, tuez les processus : `taskkill /F /PID <pid>`

**Problème : "API key not configured"**
- Vérifiez que le fichier `.env` existe à la racine du projet
- Vérifiez que les clés API sont correctes et commencent par les bons préfixes
- Redémarrez Docker : `docker-compose restart`

**Problème : "File not embedded yet"**
- Les fichiers uploadés doivent être indexés avant utilisation
- Le workflow attend automatiquement jusqu'à 60s
- Pour workflows personnalisés, utilisez `wait_for_embedding(file_id)`

**Problème : "Workflow execution timeout"**
- Timeout par défaut : 1800s (30 min) - configurable dans `config.py`
- Pour workflows longs, augmentez `max_execution_time` dans les settings
- Utilisez `asyncio.gather()` pour paralléliser les opérations indépendantes

## 📝 Technologies

**Backend** :
- FastAPI (API REST avec documentation automatique)
- Python 3.11+
- Pydantic 2.0+ (validation de données)
- aiohttp (client HTTP async)
- Upstash Redis / Vercel KV (persistance)

**Frontend** :
- HTML/CSS/JavaScript vanilla (pas de framework)
- Interface responsive avec drag-and-drop
- jsPDF (export PDF côté client dans packages)

**IA & Document Processing** :
- Anthropic Claude API (claude-sonnet-4-20250514)
- LightOn Paradigm API (recherche, analyse, extraction structurée)

**Génération de Packages** :
- ReportLab (rapports PDF serveur)
- Workflow Package Generator (UI dynamique auto-générée)
- MCP Package Generator (protocole Anthropic)

**Déploiement** :
- Docker + Docker Compose (recommandé)
- Vercel (Pro requis)
- Python/Uvicorn manuel

## 🔄 Améliorations Récentes

**v1.1.0-mcp (Janvier 2025)** :
- ✨ **MCP Server Package** : Intégration Claude Desktop et Paradigm via protocole MCP
  - Serveur dual-mode (stdio local + HTTP remote)
  - Support multi-formats d'entrée (paths, file IDs, auto-upload)
  - Configuration Docker avec bearer token auth
- ✨ **Workflow Runner Package** : Package standalone avec UI auto-générée
  - Analyse Claude du code pour génération UI intelligente
  - Support drag-and-drop fichiers
  - Export PDF intégré côté client
  - Documentation bilingue (FR/EN)

**Fonctionnalités Principales** :
- ✅ **Extraction Structurée** : `guided_choice`, `guided_regex`, `guided_json`
  - Formats garantis : SIRET, SIREN, IBAN, téléphones FR, dates, montants
  - Classification stricte avec choix prédéfinis
  - Extraction JSON avec schéma
- ✅ **Description Enhancement** : Amélioration auto des descriptions utilisateur
- ✅ **Auto-Validation** : Retry automatique (3 tentatives) avec feedback d'erreur
- ✅ **Post-Processing** : Correction auto des erreurs de syntaxe f-strings
- ✅ **Complexity Detection** : Identification workflows complexes (>40 API calls)
- ✅ **Performance** : Parallelisation auto via asyncio.gather()
- ✅ **APIs Paradigm** : Support complet (Vision OCR, filter_chunks, analyze_image, etc.)
- ✅ **Session Reuse** : Client HTTP réutilisable (5.55x plus rapide)