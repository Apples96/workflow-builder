# {WORKFLOW_NAME} - MCP Server

MCP (Model Context Protocol) server exposant le workflow "{WORKFLOW_NAME}" comme outil réutilisable.

## Description

{WORKFLOW_DESCRIPTION}

## Status des Intégrations

- ✅ **Claude Desktop** : Fonctionne parfaitement (mode stdio local)
- ⚠️ **LightOn Paradigm** : Installation réussie mais bug connu lors de l'exécution (les file_ids uploadés ne sont pas transmis au workflow)

---

## 🌐 PARTIE 1 : Déploiement pour LightOn Paradigm

### Prérequis

- Serveur avec Python 3.10+ et accès public (ex: Render, Railway, Fly.io)
- Clé API LightOn Paradigm
- Bearer token pour sécuriser l'accès MCP (optionnel mais recommandé)

### Étape 1 : Déployer le serveur HTTP sur une URL publique

Le serveur MCP HTTP doit être accessible depuis Internet pour que Paradigm puisse l'appeler.

**Option A : Déploiement sur Render.com**

1. Créez un compte sur https://render.com
2. Créez un nouveau "Web Service"
3. Connectez votre repository Git ou uploadez ce dossier
4. Configuration :
   ```
   Build Command: pip install mcp aiohttp python-dotenv uvicorn
   Start Command: python -m http_server --host 0.0.0.0 --port 10000
   ```
5. Variables d'environnement :
   ```
   PARADIGM_API_KEY=votre_clé_api
   PARADIGM_BASE_URL=https://paradigm.lighton.ai
   MCP_BEARER_TOKEN=un_token_secret_sécurisé
   ```
6. Déployez et notez l'URL publique (ex: `https://votre-app.onrender.com`)

**Option B : Déploiement sur Railway**

1. Créez un compte sur https://railway.app
2. Créez un nouveau projet et déployez depuis GitHub ou en local
3. Ajoutez les variables d'environnement
4. Le port sera automatiquement assigné

**Option C : Serveur VPS (DigitalOcean, AWS, etc.)**

```bash
# Sur votre serveur
cd /opt/mcp-servers/{WORKFLOW_NAME_SLUG}

# Installer les dépendances
pip install mcp aiohttp python-dotenv uvicorn

# Créer .env
cat > .env << EOF
PARADIGM_API_KEY=votre_clé_api
PARADIGM_BASE_URL=https://paradigm.lighton.ai
MCP_BEARER_TOKEN=votre_token_secret
EOF

# Démarrer avec systemd ou supervisord
python -m http_server --host 0.0.0.0 --port 8080
```

### Étape 2 : Enregistrer le serveur dans Paradigm

En tant qu'administrateur système dans Paradigm :

1. Allez dans **Admin > MCP Servers**
2. Cliquez sur **Add MCP Server**
3. Remplissez les informations :
   - **Name**: `{WORKFLOW_NAME_SLUG}`
   - **URL**: `https://votre-serveur.com/mcp` (l'URL publique de l'étape 1 + `/mcp`)
   - **Bearer Token**: La valeur de `MCP_BEARER_TOKEN` configurée (optionnel)
4. Cliquez sur **Save**

**⚠️ Important** : L'URL doit se terminer par `/mcp` pour que Paradigm puisse communiquer avec le serveur MCP.
   - ✅ Correct : `https://mcp-workflow-analyse-cv.onrender.com/mcp`
   - ❌ Incorrect : `https://mcp-workflow-analyse-cv.onrender.com`

### Étape 3 : Activer le serveur MCP

1. Allez dans **Chat Settings** (icône engrenage en haut à droite)
2. Section **Agent Tools**
3. Activez le toggle pour `{WORKFLOW_NAME_SLUG}`
4. Activez le **Mode Agent** dans vos conversations

### ⚠️ Bug Connu Paradigm

**Problème** : Les fichiers uploadés via l'interface Paradigm ne sont pas correctement transmis au workflow MCP.

**Symptôme** : Le workflow reçoit des `file_ids` vides ou incorrects, même si vous avez uploadé des documents.

**Status** : Bug en cours d'investigation avec l'équipe Paradigm.

**Workaround temporaire** : Utilisez Claude Desktop en local (voir Partie 2) où tout fonctionne correctement.

---

## 🖥️ PARTIE 2 : Installation pour Claude Desktop

### Prérequis

- Python 3.10 ou supérieur installé
- Claude Desktop installé (https://claude.ai/download)

### Étape 1 : Installer les dépendances Python (une seule fois)

**IMPORTANT :** Installez les dépendances globalement, une seule fois pour tous vos workflows MCP !

```bash
pip install mcp aiohttp python-dotenv
```

⚠️ **NE FAITES PAS** `pip install -e .` dans ce dossier ! Cela créerait des conflits si vous avez plusieurs workflows MCP.

### Étape 2 : Configurer le fichier .env

Un fichier `.env.example` est présent dans ce dossier. Renommez-le en `.env` et remplissez votre clé API Paradigm :

```bash
# Renommer le fichier
mv .env.example .env

# Éditer le fichier .env et remplacer "votre_clé_api" par votre vraie clé
PARADIGM_API_KEY=votre_clé_api_ici
PARADIGM_BASE_URL=https://paradigm.lighton.ai
```

Vous pouvez obtenir votre clé API depuis : https://paradigm.lighton.ai/settings/api-keys

### Étape 3 : Configurer Claude Desktop

Ajoutez cette configuration dans le fichier de configuration de Claude Desktop.

**Localisation du fichier :**

- **Windows** : `%APPDATA%\Claude\claude_desktop_config.json`
  - Chemin complet : `C:\Users\VotreNom\AppData\Roaming\Claude\claude_desktop_config.json`
  - Ouvrir le dossier : Tapez `%APPDATA%\Claude` dans l'explorateur Windows

- **macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`

- **Linux** : `~/.config/Claude/claude_desktop_config.json`

**Configuration à ajouter :**

```json
{{
  "mcpServers": {{
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "py",
      "args": ["-3.10", "-m", "server"],
      "cwd": "CHEMIN_ABSOLU_VERS_CE_DOSSIER"
    }}
  }}
}}
```

**⚠️ IMPORTANT - Remplacez `CHEMIN_ABSOLU_VERS_CE_DOSSIER` :**

Exemples :
- Windows : `"cwd": "C:\\Users\\VotreNom\\Downloads\\{WORKFLOW_NAME_SLUG}"`
- macOS/Linux : `"cwd": "/Users/VotreNom/Downloads/{WORKFLOW_NAME_SLUG}"`

**Notes :**
- Utilisez des doubles backslashes `\\` sur Windows
- Le chemin doit être absolu (pas de `~` ou variables d'environnement)
- Si vous avez Python 3.11+, remplacez `-3.10` par votre version

**Si vous avez déjà d'autres serveurs MCP :**

```json
{{
  "mcpServers": {{
    "autre-serveur": {{
      "command": "...",
      "args": [...]
    }},
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "py",
      "args": ["-3.10", "-m", "server"],
      "cwd": "CHEMIN_ABSOLU_VERS_CE_DOSSIER"
    }}
  }}
}}
```

### Étape 4 : Redémarrer Claude Desktop

1. Fermez **complètement** Claude Desktop (vérifiez qu'il n'est pas dans la barre des tâches)
2. Relancez Claude Desktop
3. Le serveur MCP `{WORKFLOW_NAME_SLUG}` sera chargé automatiquement

### Vérification

Dans Claude Desktop, vous devriez voir une notification indiquant que le serveur MCP est connecté.

Si vous voyez une erreur, consultez les logs :
- **Windows** : Menu **Help > Show Logs**
- **macOS** : Menu **Claude > Show Logs**

---

## 📖 Utilisation

### Dans Claude Desktop

Une fois configuré, utilisez le workflow directement dans vos conversations en spécifiant les **chemins absolus** des documents à analyser :

{USAGE_EXAMPLES}

**Important** : Claude Desktop nécessite les chemins complets des fichiers sur votre système (ex: `C:\Users\VotreNom\Documents\mon_cv.pdf` sur Windows ou `/Users/VotreNom/Documents/mon_cv.pdf` sur macOS/Linux).

**⚠️ Limite de temps Claude Desktop** : Claude Desktop impose un timeout de **4 minutes maximum** par requête MCP. Si votre workflow traite beaucoup de documents ou effectue des analyses complexes qui dépassent ce délai, la requête sera annulée avec un message "Request timed out".

**Recommandations** :
- Limitez le nombre de documents analysés simultanément (idéalement 3-5 maximum)
- Pour des workflows longs, préférez le déploiement HTTP sur Paradigm qui n'a pas cette limitation
- Si le timeout se produit, essayez de simplifier le workflow ou de réduire le nombre de fichiers traités

Claude utilisera automatiquement l'outil MCP pour exécuter le workflow.

### Dans Paradigm (une fois le bug résolu)

1. Uploadez vos documents via l'interface Paradigm
2. Activez le **Mode Agent** dans la conversation
3. Demandez à Paradigm d'utiliser le workflow :
   ```
   Utilise le workflow {WORKFLOW_NAME_SLUG} pour analyser les documents uploadés
   ```

---

## 📊 Paramètres du Workflow

{WORKFLOW_PARAMETERS_DOC}

## 📤 Format de Sortie

{WORKFLOW_OUTPUT_DOC}

---

## 🔧 Dépannage

### Claude Desktop

**Le serveur ne démarre pas**
- Vérifiez que Python 3.10+ est installé : `python --version` ou `py -3.10 --version`
- Vérifiez les dépendances : `pip list | grep mcp`
- Consultez les logs Claude Desktop : Menu **Help > Show Logs**

**Erreur "command not found"**
- Sur Windows, utilisez `"command": "py"` au lieu de `"command": "python"`
- Spécifiez le chemin complet : `"command": "C:\\Python310\\python.exe"`

**Erreur d'authentification Paradigm**
- Vérifiez que votre clé API est correcte dans le fichier `.env`
- Testez la clé : `curl -H "Authorization: Bearer VOTRE_CLE" https://paradigm.lighton.ai/api/v2/health`

**Le workflow échoue**
- Vérifiez que vous avez bien uploadé les fichiers requis
- Consultez les logs pour voir les détails de l'erreur
- Vérifiez que les paramètres respectent le schéma attendu

### Paradigm

**Le serveur MCP n'apparaît pas**
- Vérifiez que l'URL publique est accessible : `curl https://votre-serveur.com/health`
- Vérifiez le bearer token configuré
- Contactez votre administrateur système Paradigm

**Bug des file_ids**
- C'est un problème connu, utilisez Claude Desktop en attendant la correction

---

## 📁 Structure du Projet

```
{WORKFLOW_NAME_SLUG}/
├── server.py              # Serveur MCP stdio (Claude Desktop)
├── http_server.py         # Serveur MCP HTTP (Paradigm)
├── workflow.py            # Logique du workflow générée
├── paradigm_client.py     # Client API Paradigm standalone
├── pyproject.toml         # Configuration package Python
├── .env                   # Variables d'environnement (déjà configuré)
├── .env.example           # Template variables d'environnement
├── .gitignore             # Fichiers à ignorer par Git
└── README.md              # Ce fichier
```

---

## 📞 Support

- **Documentation MCP** : https://modelcontextprotocol.io
- **Documentation Paradigm** : https://docs.lighton.ai
- **Support LightOn** : support@lighton.ai

---

**Généré par LightOn Workflow Builder**
