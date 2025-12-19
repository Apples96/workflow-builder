# {WORKFLOW_NAME} - MCP Server

MCP (Model Context Protocol) server exposant le workflow "{WORKFLOW_NAME}" comme outil réutilisable.

## Description

{WORKFLOW_DESCRIPTION}

Ce serveur MCP permet d'utiliser ce workflow directement depuis:
- **Claude Desktop** - Assistant IA avec accès aux outils MCP
- **LightOn Paradigm** - Plateforme IA (support MCP à venir)
- **Tout client compatible MCP** - Via le protocole standardisé

## Prérequis

- Python 3.10 ou supérieur
- Clé API LightOn Paradigm (https://paradigm.lighton.ai)
- Accès aux documents dans votre workspace Paradigm

## Installation

### 1. Installer les dépendances communes (une seule fois)

**IMPORTANT:** N'installez les dépendances qu'une seule fois, pas pour chaque workflow !

```bash
pip install mcp aiohttp python-dotenv
```

⚠️ **NE FAITES PAS** `pip install -e .` dans ce dossier ! Cela créerait des conflits si vous avez plusieurs workflows MCP.

### 2. Configurer les variables d'environnement

Créez un fichier `.env` à la racine du package:

```bash
PARADIGM_API_KEY=votre_clé_api_ici
PARADIGM_BASE_URL=https://paradigm.lighton.ai
```

### 3. Configuration pour Claude Desktop

Ajoutez cette configuration dans le fichier de configuration de Claude Desktop:

**macOS/Linux:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:**
```powershell
# Ouvrir directement le fichier avec l'explorateur
start "" "%APPDATA%\Claude"
# Puis ouvrir claude_desktop_config.json avec un éditeur de texte
```

Ou via l'explorateur Windows :
1. Tapez `%APPDATA%\Claude` dans la barre d'adresse de l'explorateur
2. Ouvrez le fichier `claude_desktop_config.json` avec un éditeur de texte

```json
{{
  "mcpServers": {{
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/chemin/absolu/vers/ce/dossier"
    }}
  }}
}}
```

**Notes:**
- Le chemin `cwd` doit pointer vers le dossier où se trouve ce package
- La commande `command` doit pointer vers votre exécutable Python 3.10+ (sous Windows, utilisez le chemin complet comme `C:\\Users\\VotreNom\\AppData\\Local\\Programs\\Python\\Python310\\python.exe`)
- Le fichier `.env` dans le dossier `cwd` contient déjà les variables d'environnement (pas besoin de les mettre dans `env`)

### 4. Redémarrer Claude Desktop

Fermez complètement Claude Desktop et relancez-le. Le nouvel outil MCP sera disponible.

## Utilisation

### Dans Claude Desktop

Une fois configuré, vous pouvez utiliser le workflow directement dans vos conversations:

{USAGE_EXAMPLES}

### Test en ligne de commande

Pour tester le serveur MCP en ligne de commande:

```bash
python -m server
```

Le serveur démarre et attend les commandes MCP via stdin/stdout.

## Structure du projet

```
{WORKFLOW_NAME_SLUG}/
├── server.py              # Serveur MCP principal
├── workflow.py            # Logique du workflow
├── paradigm_client.py     # Client API Paradigm
├── pyproject.toml         # Configuration Python
├── README.md              # Ce fichier
└── .env                   # Variables d'environnement (à créer)
```

## Paramètres du workflow

{WORKFLOW_PARAMETERS_DOC}

## Format de sortie

{WORKFLOW_OUTPUT_DOC}

## Dépannage

### Le serveur ne démarre pas

- Vérifiez que Python 3.10+ est installé: `python --version`
- Vérifiez que les dépendances sont installées: `pip install -e .`
- Vérifiez les logs dans Claude Desktop (menu Developer > Show Logs)

### Erreur d'authentification Paradigm

- Vérifiez que votre clé API est correcte dans `.env` ou `claude_desktop_config.json`
- Testez la clé avec: `curl -H "Authorization: Bearer VOTRE_CLE" https://paradigm.lighton.ai/api/v2/health`

### Le workflow échoue

- Vérifiez que les documents nécessaires sont bien dans votre workspace Paradigm
- Consultez les logs pour voir les détails de l'erreur
- Vérifiez que les paramètres d'entrée respectent le schéma attendu

## Support

Pour toute question ou problème:
- Documentation MCP: https://modelcontextprotocol.io
- Documentation Paradigm: https://docs.lighton.ai
- Support LightOn: support@lighton.ai

## Licence

Généré par LightOn Workflow Builder
