# LightOn Workflow Builder

Application de génération et d'exécution de workflows automatisés utilisant l'API Anthropic Claude et l'API LightOn Paradigm.

## 🚀 Démarrage Rapide

### Développement quotidien
Double-cliquez sur **`dev.bat`**
- Démarre le serveur en mode développement
- Frontend : http://localhost:3000
- Backend API : http://localhost:8000/docs

### Test avant déploiement
Double-cliquez sur **`test-docker.bat`**
- Teste l'application dans Docker (environnement de production)
- Vérifiez que tout fonctionne avant de déployer

## 📋 Prérequis

1. **Python 3.11+** installé
2. **Docker Desktop** (pour les tests Docker uniquement)
3. **Fichier .env** avec vos clés API :
   ```env
   ANTHROPIC_API_KEY=votre_clé_anthropic
   LIGHTON_API_KEY=votre_clé_lighton
   ```

## 🛠️ Workflow de Développement

```
1. Développer        → dev.bat
2. Tester            → http://localhost:3000
3. Test Docker       → test-docker.bat (avant commit)
4. Commit & Push     → git commit && git push
5. Déploiement       → Automatique sur Vercel
```

## ✨ Fonctionnalités Principales

### 1. Création de Workflows IA
- **Natural Language to Code**: Décrivez vos workflows en langage naturel
- **AI-Powered Generation**: Génération de code Python par Anthropic Claude
- **Auto-Validation**: Validation automatique avec retry (jusqu'à 3 tentatives)
- **Post-Processing**: Correction automatique des erreurs f-strings

### 2. Intégration Complète LightOn Paradigm
- **Document Search**: Recherche sémantique dans vos documents
- **Document Analysis**: Analyse approfondie avec polling automatique
- **Vision OCR**: Support de VisionDocumentSearch pour documents scannés
- **File Management**: Upload, indexation automatique, gestion de fichiers
- **Advanced Features**: Filter chunks, get file chunks, query sans AI

### 3. Exécution Sécurisée et Performance
- **Safe Execution**: Environnement sandboxé avec timeout (30 min par défaut)
- **File Attachments**: Support de fichiers joints aux workflows
- **Redis Storage**: Persistance avec Upstash Redis pour serverless
- **Performance**: Session reuse HTTP (5.55x plus rapide)

### 4. Export et Déploiement Client
- **PDF Reports**: Génération de rapports professionnels
- **Workflow Runner**: Package ZIP standalone avec frontend dynamique + backend complet
  - Interface utilisateur générée automatiquement selon le workflow
  - Documentation bilingue (FR/EN)
  - Configuration Docker incluse
  - Prêt pour déploiement client autonome
  - ⚠️ Disponible en mode développement local uniquement (désactivé sur Vercel)
- **RESTful API**: API FastAPI avec documentation OpenAPI automatique

## 🔧 Installation Manuelle (si besoin)

1. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configurer les clés API**

   Créez un fichier `.env` à la racine :
   ```bash
   ANTHROPIC_API_KEY=votre_clé_anthropic
   LIGHTON_API_KEY=votre_clé_lighton

   # Redis (optionnel - pour persistance serverless)
   # Vercel KV (automatique si lié depuis Vercel)
   KV_REST_API_URL=https://your-redis.upstash.io
   KV_REST_API_TOKEN=your_token_here

   # OU Upstash direct (configuration manuelle)
   UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
   UPSTASH_REDIS_REST_TOKEN=your_token_here
   ```

3. **Démarrer le serveur**
   ```bash
   # Utilisez plutôt dev.bat (recommandé)
   # Ou manuellement :
   python -m uvicorn api.index:app --port 8000
   ```

## 📖 API Endpoints

### Workflows
- `POST /api/workflows` - Créer un workflow depuis une description
- `POST /api/workflows/enhance-description` - Améliorer une description avec l'IA
- `GET /api/workflows/{id}` - Récupérer les détails d'un workflow
- `POST /api/workflows/{id}/execute` - Exécuter un workflow
- `GET /api/workflows/{id}/executions/{exec_id}` - Détails d'exécution
- `GET /api/workflows/{id}/executions/{exec_id}/pdf` - Télécharger rapport PDF
- `POST /api/workflow/generate-package/{id}` - Générer package ZIP (local uniquement)

### Files
- `POST /api/files/upload` - Uploader un fichier
- `GET /api/files/{id}` - Info sur un fichier
- `DELETE /api/files/{id}` - Supprimer un fichier

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

Les workflows générés ont accès à un **ParadigmClient complet** avec toutes les APIs LightOn :

### Recherche et Analyse
- `document_search(query, file_ids=...)` - Recherche sémantique
- `analyze_documents_with_polling(query, document_ids)` - Analyse approfondie
- `chat_completion(prompt, guided_choice=..., guided_regex=...)` - Complétion avec extraction structurée
  - **guided_choice** : Force le choix parmi une liste (ex: ["oui", "non"])
  - **guided_regex** : Force un format précis (SIRET, IBAN, téléphone, etc.)

### Gestion de Fichiers
- `upload_file(file_content, filename)` - Upload de fichiers
- `get_file(file_id)` - Informations sur un fichier
- `wait_for_embedding(file_id)` - Attendre l'indexation
- `get_file_chunks(file_id)` - Récupérer les chunks d'un fichier

### APIs Avancées
- `filter_chunks(query, chunk_ids, n=...)` - Filtrer les chunks par pertinence
- `query(query, collection=...)` - Extraire chunks sans synthèse AI
- `search_with_vision_fallback(query, file_ids)` - Recherche avec OCR automatique

### Extraction de Données Structurées (NOUVEAU ✨)

Les workflows peuvent utiliser **guided_choice** et **guided_regex** pour extraire des données avec garantie de format :

```python
# Extraction de SIRET avec format garanti (14 chiffres)
siret = await paradigm_client.chat_completion(
    prompt="Extrais le numéro SIRET",
    guided_regex=r"\\d{14}"
)

# Classification stricte
status = await paradigm_client.chat_completion(
    prompt="Le document est-il conforme ?",
    guided_choice=["conforme", "non_conforme", "incomplet"]
)
```

**Patterns regex prédéfinis inclus** : SIRET, SIREN, IBAN, téléphone FR, dates, montants, emails.

📖 **Guide complet** : Voir [GUIDED_FEATURES.md](GUIDED_FEATURES.md)

### Support de Session
Toutes les méthodes supportent le `session` parameter pour réutiliser les connexions HTTP (5.55x plus rapide).

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

# Test Docker (avant commit)
./test-docker.bat
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
├── vercel.json                  # Configuration Vercel
├── dev.bat                      # Script de développement Windows
└── test-docker.bat              # Script de test Docker
```

## 🐳 Déploiement du Workflow Builder

### Option A : Docker (Recommandé - Le plus simple)

Déployer le workflow builder complet avec Docker pour un environnement prêt à l'emploi.

```bash
# 1. Cloner le repository
git clone https://github.com/Isydoria/lighton-workflow-generator-.git
cd lighton-workflow-generator-

# 2. Configurer les clés API
cp .env.example .env
# Éditer .env et ajouter :
# ANTHROPIC_API_KEY=your_anthropic_key
# LIGHTON_API_KEY=your_lighton_key

# 3. Démarrer avec Docker Compose
docker-compose up --build

# 4. Accéder à l'interface
# Frontend : http://localhost:3000
# API Backend : http://localhost:8000/docs

# Arrêt
docker-compose down
```

**✅ Avantages** :
- Configuration minimale
- Environnement isolé et reproductible
- Prêt pour production (déployable sur n'importe quel serveur avec Docker)
- Pas de limite de functions serverless

### Option B : Vercel (Requires Pro Plan)

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

### Option C : Déploiement Python Manuel

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
- Les scripts `dev.bat` et `test-docker.bat` tuent automatiquement les anciens serveurs
- Si problème persiste : `powershell "Get-Process python | Stop-Process -Force"`

**Problème : "API key not configured"**
- Vérifiez que le fichier `.env` existe à la racine du projet
- Vérifiez que les clés API sont correctes et commencent par les bons préfixes
- Redémarrez avec `dev.bat`

**Problème : "File not embedded yet"**
- Les fichiers uploadés doivent être indexés avant utilisation
- Le workflow attend automatiquement jusqu'à 60s
- Pour workflows personnalisés, utilisez `wait_for_embedding(file_id)`

**Problème : "Workflow execution timeout"**
- Timeout par défaut : 1800s (30 min) - configurable dans `config.py`
- Pour workflows longs, augmentez `max_execution_time` dans les settings
- Utilisez `asyncio.gather()` pour paralléliser les opérations indépendantes

## 📝 Technologies

- **Backend** : FastAPI, Python 3.11+, aiohttp, Upstash Redis
- **Frontend** : HTML/CSS/JavaScript vanilla
- **AI** : Anthropic Claude API (claude-sonnet-4-20250514)
- **Document Processing** : LightOn Paradigm API (toutes les fonctionnalités)
- **PDF Generation** : ReportLab
- **Déploiement** : Vercel (prod), Docker (test/local)

## 🔄 Améliorations Récentes

- ✨ **NOUVEAU** : Support de `guided_choice` et `guided_regex` pour extraction structurée
  - Extraction garantie de SIRET, IBAN, téléphones avec format validé
  - Classification stricte avec choix prédéfinis
  - Patterns regex prédéfinis pour formats français
- ✅ Post-validation automatique des f-strings générées
- ✅ Support complet de toutes les APIs Paradigm (Vision OCR, filter chunks, etc.)
- ✅ Retry automatique avec contexte d'erreur (3 tentatives)
- ✅ Normalisation de données (IBAN, SIRET, téléphones)
- ✅ Détection et correction des workflows complexes (>40 API calls)