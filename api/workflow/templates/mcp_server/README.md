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

### 1. Installer le package

```bash
pip install -e .
```

### 2. Configurer les variables d'environnement

Créez un fichier `.env` à la racine du package:

```bash
PARADIGM_API_KEY=votre_clé_api_ici
PARADIGM_BASE_URL=https://paradigm.lighton.ai
```

### 3. Configuration pour Claude Desktop

Ajoutez cette configuration dans le fichier de configuration de Claude Desktop:

**macOS/Linux:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{{
  "mcpServers": {{
    "{WORKFLOW_NAME_SLUG}": {{
      "command": "python",
      "args": [
        "-m",
        "server"
      ],
      "cwd": "/chemin/absolu/vers/ce/dossier",
      "env": {{
        "PARADIGM_API_KEY": "votre_clé_api_ici",
        "PARADIGM_BASE_URL": "https://paradigm.lighton.ai"
      }}
    }}
  }}
}}
```

**Important:** Remplacez `/chemin/absolu/vers/ce/dossier` par le chemin complet vers ce dossier.

### 4. Redémarrer Claude Desktop

Fermez complètement Claude Desktop et relancez-le. Le nouvel outil MCP sera disponible.

## Utilisation

### Dans Claude Desktop

Une fois configuré, vous pouvez utiliser le workflow directement dans vos conversations:

{USAGE_EXAMPLES}

### Test en ligne de commande

Pour tester le serveur MCP en ligne de commande:

```bash
python server.py
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
