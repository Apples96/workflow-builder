# {{WORKFLOW_NAME}}

Application standalone générée automatiquement par **LightOn Workflow Builder**.

## 📋 Description

{{WORKFLOW_DESCRIPTION}}

## 🚀 Installation et démarrage rapide

### Prérequis

- **Docker** et **Docker Compose** installés sur votre machine
  - Windows/Mac: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - Linux: [Docker Engine](https://docs.docker.com/engine/install/)
- Une clé API Paradigm (obtenez-la sur [paradigm.lighton.ai](https://paradigm.lighton.ai))

### Étapes d'installation

**1. Configurer votre clé API**

Créez un fichier `.env` à la racine du projet :

```bash
# Sur Windows (PowerShell)
copy .env.example .env

# Sur Mac/Linux
cp .env.example .env
```

Éditez le fichier `.env` et remplacez `your_paradigm_api_key_here` par votre vraie clé API :

```env
PARADIGM_API_KEY=sk-votre-cle-api-ici
```

**2. Lancer l'application**

```bash
docker-compose up -d
```

**Cette commande va :**
- Construire l'image Docker
- Installer toutes les dépendances
- Démarrer l'application en arrière-plan

**3. Accéder à l'interface**

Ouvrez votre navigateur et allez sur :

```
http://localhost:8000
```

Vous verrez l'interface de votre workflow !

## 📖 Utilisation

### Interface web

1. **Uploadez vos fichiers** (si nécessaire)
   - Glissez-déposez vos fichiers dans les zones prévues
   - Ou cliquez pour sélectionner depuis votre ordinateur

2. **Entrez votre texte** (si nécessaire)
   - Remplissez le champ de texte avec votre requête

3. **Cliquez sur "Exécuter le workflow"**
   - L'analyse démarre automatiquement
   - Les résultats s'affichent après quelques secondes

4. **Téléchargez le rapport PDF**
   - Cliquez sur "📄 Télécharger le rapport PDF"
   - Le PDF contient tous les résultats formatés

### Commandes utiles

```bash
# Voir les logs en temps réel
docker-compose logs -f

# Arrêter l'application
docker-compose down

# Redémarrer l'application
docker-compose restart

# Reconstruire après modification
docker-compose up -d --build
```

## 🛠️ Personnalisation

### Modifier l'interface

Les fichiers de l'interface se trouvent dans `frontend/` :
- `index.html` : Structure de la page
- `config.json` : Configuration (noms des fichiers, labels, etc.)

### Modifier le workflow

Le code du workflow se trouve dans `backend/workflow.py`.

**⚠️ Attention** : Si vous modifiez le workflow, vous devrez peut-être adapter l'interface en conséquence.

## 📁 Structure du projet

```
{{WORKFLOW_NAME}}/
├── backend/
│   ├── main.py              # Serveur FastAPI
│   ├── workflow.py          # Code du workflow
│   ├── paradigm_client.py   # Client API Paradigm
│   └── requirements.txt     # Dépendances Python
│
├── frontend/
│   ├── index.html          # Interface web
│   └── config.json         # Configuration
│
├── docker-compose.yml      # Configuration Docker Compose
├── Dockerfile             # Image Docker
├── .env.example           # Exemple de configuration
├── .env                   # Votre configuration (NE PAS COMMITER!)
└── README.md              # Ce fichier
```

## 🔧 Dépannage

### Problème : "Port 8000 already in use"

Un autre service utilise déjà le port 8000. Solutions :

1. **Arrêter l'autre service** ou
2. **Changer le port** dans `docker-compose.yml` :
   ```yaml
   ports:
     - "8001:8000"  # Utiliser le port 8001 à la place
   ```
   Puis accédez à `http://localhost:8001`

### Problème : "API key not configured"

Vérifiez que :
1. Le fichier `.env` existe à la racine du projet
2. La clé API est correcte (commence par `sk-...`)
3. Vous avez redémarré l'application après avoir modifié `.env`

```bash
docker-compose down
docker-compose up -d
```

### Problème : "Failed to upload file"

Vérifiez que :
1. Votre clé API Paradigm est valide
2. Vous avez accès à Internet
3. Le fichier n'est pas trop volumineux (limite : 100 MB)

### Voir les logs détaillés

```bash
docker-compose logs -f workflow-runner
```

## 🔒 Sécurité

- ⚠️ **Ne partagez JAMAIS votre clé API** publiquement
- ⚠️ **Ne committez PAS le fichier `.env`** dans Git
- ✅ Le fichier `.env` est déjà dans `.gitignore` par défaut

## 📚 Documentation

- **API Paradigm** : [paradigm.lighton.ai/docs](https://paradigm.lighton.ai/docs)
- **LightOn Workflow Builder** : Documentation du système qui a généré cette application
- **Docker** : [docs.docker.com](https://docs.docker.com)

## 🆘 Support

Pour toute question ou problème :
1. Consultez la documentation de Paradigm
2. Vérifiez les logs avec `docker-compose logs`
3. Contactez le support technique de LightOn

---

**Généré automatiquement par LightOn Workflow Builder**
Version: 1.0.0
Date: {{GENERATION_DATE}}
