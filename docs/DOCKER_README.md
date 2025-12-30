# 🐳 Docker Deployment Guide

Guide complet pour déployer l'application LightOn Workflow Generator avec Docker.

---

## 📋 Table des matières

- [Prérequis](#prérequis)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Commandes Docker](#commandes-docker)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Production](#production)

---

## 🎯 Prérequis

### Logiciels requis

- **Docker** : Version 20.10 ou supérieure
- **Docker Compose** : Version 2.0 ou supérieure

### Vérification de l'installation

```bash
docker --version
docker-compose --version
```

### Installation de Docker

**Windows / macOS** :
- Télécharger et installer [Docker Desktop](https://www.docker.com/products/docker-desktop)

**Linux** :
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose

# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER
```

---

## 🚀 Quick Start

### 1. Configurer les variables d'environnement

Créez un fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Éditez le fichier `.env` et ajoutez vos clés API :

```env
# Anthropic API (pour la génération de code)
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# LightOn Paradigm API (pour les workflows)
PARADIGM_API_KEY=your-paradigm-api-key-here
PARADIGM_API_BASE_URL=https://paradigm.lighton.ai
```

### 2. Démarrer l'application

```bash
docker-compose up
```

L'application sera disponible sur :
- **Frontend** : http://localhost:3000
- **Backend API** : http://localhost:8000
- **API Documentation** : http://localhost:8000/docs

### 3. Arrêter l'application

```bash
# Arrêt gracieux
docker-compose down

# Arrêt et suppression des volumes
docker-compose down -v
```

---

## ⚙️ Configuration

### Variables d'environnement

| Variable | Description | Requis | Défaut |
|----------|-------------|---------|---------|
| `ANTHROPIC_API_KEY` | Clé API Anthropic pour Claude | Oui | - |
| `PARADIGM_API_KEY` | Clé API LightOn Paradigm | Oui | - |
| `PARADIGM_API_BASE_URL` | URL de base de l'API Paradigm | Non | `https://paradigm.lighton.ai` |
| `KV_REST_API_URL` | URL Vercel KV (automatique si lié) | Non | - |
| `KV_REST_API_TOKEN` | Token Vercel KV (automatique si lié) | Non | - |
| `UPSTASH_REDIS_REST_URL` | URL Upstash Redis (config manuelle) | Non | - |
| `UPSTASH_REDIS_REST_TOKEN` | Token Upstash Redis (config manuelle) | Non | - |
| `PYTHONUNBUFFERED` | Désactive le buffering Python | Non | `1` |

**Note** : Pour Redis, utilisez soit les variables Vercel KV (automatiques), soit les variables Upstash directes (manuelles). Le code supporte les deux conventions avec fallback automatique.

### Ports exposés

- **3000** : Frontend (serveur HTTP statique)
- **8000** : Backend FastAPI

Pour changer les ports, modifiez le fichier `docker-compose.yml` :

```yaml
ports:
  - "8080:8000"  # Backend sur port 8080
  - "3001:3000"  # Frontend sur port 3001
```

---

## 🛠️ Commandes Docker

### Build et Run

```bash
# Build l'image Docker
docker build -t lighton-workflow-generator .

# Run le container
docker run -p 8000:8000 -p 3000:3000 \
  -e ANTHROPIC_API_KEY=your-key \
  -e PARADIGM_API_KEY=your-key \
  lighton-workflow-generator

# Avec docker-compose (recommandé)
docker-compose up -d  # Démarrage en arrière-plan
```

### Logs

```bash
# Voir les logs en temps réel
docker-compose logs -f

# Logs d'un service spécifique
docker-compose logs -f workflow-generator

# Dernières 100 lignes
docker-compose logs --tail=100
```

### Commandes utiles

```bash
# Lister les containers en cours
docker-compose ps

# Entrer dans le container (shell interactif)
docker-compose exec workflow-generator /bin/bash

# Redémarrer les services
docker-compose restart

# Rebuild après modifications du code
docker-compose up --build

# Supprimer tous les containers et images
docker-compose down --rmi all
```

---

## 🏗️ Architecture

### Structure de l'image Docker

```
Dockerfile (multi-stage build)
├── Stage 1: Base
│   └── Python 3.12 slim + dépendances système
├── Stage 2: Dependencies
│   └── Installation des packages Python
└── Stage 3: Runtime
    ├── Copie des dépendances
    ├── Copie du code source
    ├── User non-root (appuser)
    └── Health check
```

### Optimisations

1. **Multi-stage build** : Réduit la taille de l'image finale
2. **Layer caching** : Les dépendances sont cachées pour des builds plus rapides
3. **Non-root user** : Sécurité renforcée
4. **Health checks** : Surveillance automatique de l'état de l'application

### Taille de l'image

- **Image de base** : ~150 MB (Python 3.12 slim)
- **Avec dépendances** : ~450 MB
- **Image finale** : ~500 MB

---

## 🔧 Développement

### Mode développement avec hot reload

Le fichier `docker-compose.yml` inclut des volumes pour le développement :

```yaml
volumes:
  - ./api:/app/api
  - ./frontend:/app/frontend
  - ./index.html:/app/index.html
```

Les modifications du code seront reflétées immédiatement sans rebuild.

### Désactiver les volumes pour la production

Commentez les lignes `volumes` dans `docker-compose.yml` :

```yaml
# volumes:
#   - ./api:/app/api
#   - ./frontend:/app/frontend
```

### Rebuild après modifications du Dockerfile

```bash
docker-compose up --build
```

---

## 🐛 Troubleshooting

### Problème : Container ne démarre pas

**Solution** :
```bash
# Voir les logs d'erreur
docker-compose logs workflow-generator

# Vérifier l'état du container
docker-compose ps
```

### Problème : Port déjà utilisé

**Erreur** : `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Solution** :
```bash
# Trouver le processus utilisant le port
# Windows
netstat -ano | findstr :8000

# Linux/macOS
lsof -i :8000

# Changer le port dans docker-compose.yml
ports:
  - "8080:8000"
```

### Problème : Variables d'environnement non chargées

**Solution** :
```bash
# Vérifier que le fichier .env existe
ls -la .env

# Recréer les containers
docker-compose down
docker-compose up
```

### Problème : Erreur "No module named 'api'"

**Solution** :
```bash
# Rebuild l'image
docker-compose up --build

# Ou forcer la reconstruction
docker-compose build --no-cache
```

### Problème : Health check failing

**Solution** :
```bash
# Vérifier que le endpoint /health existe dans l'API
# Augmenter le start_period dans docker-compose.yml
healthcheck:
  start_period: 60s  # Au lieu de 40s
```

---

## 🗄️ Configuration Redis (Upstash / Vercel KV)

### Pourquoi Redis ?

L'application supporte Upstash Redis pour le stockage persistant des workflows, particulièrement utile dans les environnements serverless comme Vercel :

- **Avec Redis** : Les workflows persistent entre les redémarrages de containers et les instances serverless
- **Sans Redis** : Fallback vers stockage en mémoire (workflows perdus au redémarrage)

### Configuration automatique avec Vercel KV

**Option recommandée pour Vercel** :

1. Dans votre projet Vercel, allez dans "Storage" → "Create Database" → "KV"
2. Liez la base de données à votre projet
3. Vercel crée automatiquement les variables :
   - `KV_REST_API_URL`
   - `KV_REST_API_TOKEN`
4. Le code détecte et utilise automatiquement ces variables

**Aucune configuration manuelle nécessaire** ! Le code supporte nativement les variables Vercel KV.

### Configuration manuelle avec Upstash

**Option pour Docker ou configuration personnalisée** :

```bash
# Ajoutez les variables dans votre .env
UPSTASH_REDIS_REST_URL=https://your-redis-instance.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-redis-token-here
```

**Obtenir des credentials Upstash** :

1. Créer un compte sur [Upstash](https://upstash.com/)
2. Créer une base de données Redis
3. Copier l'URL REST et le token
4. Ajouter les credentials dans `.env`

### Compatibilité des variables

Le code supporte **les deux conventions** automatiquement avec fallback :

```python
# Priorité 1 : Vercel KV (variables créées automatiquement)
redis_url = os.getenv("KV_REST_API_URL")
redis_token = os.getenv("KV_REST_API_TOKEN")

# Priorité 2 : Upstash direct (configuration manuelle)
if not redis_url:
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
if not redis_token:
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
```

Ceci garantit une compatibilité maximale sans configuration supplémentaire.

### Mode développement sans Redis

Redis est **optionnel** pour le développement local. Si les variables ne sont pas configurées :
- L'application démarre normalement
- Les workflows sont stockés en mémoire
- Un warning apparaît dans les logs : `⚠️ upstash-redis not installed, using in-memory storage`

### TTL (Time To Live)

Les workflows stockés dans Redis ont une durée de vie de **24 heures** :
- Nettoyage automatique après expiration
- Pas de maintenance manuelle nécessaire
- Configurable dans `api/workflow/executor.py` (ligne 62)

---

## 🚀 Production

### Build pour production

```bash
# Build avec tag de version
docker build -t lighton-workflow-generator:1.0.0 .

# Tag pour registry
docker tag lighton-workflow-generator:1.0.0 \
  registry.example.com/lighton-workflow-generator:1.0.0

# Push vers registry
docker push registry.example.com/lighton-workflow-generator:1.0.0
```

### docker-compose.prod.yml

Créez un fichier séparé pour la production :

```yaml
version: '3.8'

services:
  workflow-generator:
    image: lighton-workflow-generator:1.0.0
    container_name: lighton-workflow-generator-prod
    ports:
      - "8000:8000"
      - "3000:3000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - PARADIGM_API_KEY=${PARADIGM_API_KEY}
      - PARADIGM_API_BASE_URL=${PARADIGM_API_BASE_URL}
      - UPSTASH_REDIS_REST_URL=${UPSTASH_REDIS_REST_URL}
      - UPSTASH_REDIS_REST_TOKEN=${UPSTASH_REDIS_REST_TOKEN}
    env_file:
      - .env.production
    restart: always
    networks:
      - workflow-network
    # PAS de volumes pour la production

networks:
  workflow-network:
    driver: bridge
```

### Déployer en production

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Reverse proxy (Nginx)

Configuration Nginx recommandée :

```nginx
server {
    listen 80;
    server_name workflow.example.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📊 Monitoring

### Vérifier l'état de santé

```bash
# Avec Docker
docker inspect --format='{{.State.Health.Status}}' lighton-workflow-generator

# Avec curl
curl http://localhost:8000/health
```

### Logs structurés

```bash
# Filtrer les logs par niveau
docker-compose logs | grep ERROR
docker-compose logs | grep WARNING

# Export des logs
docker-compose logs > application.log
```

---

## 🔐 Sécurité

### Bonnes pratiques

1. ✅ **Utilisateur non-root** : Le container s'exécute avec l'utilisateur `appuser`
2. ✅ **Secrets** : Les API keys sont passées via variables d'environnement
3. ✅ **Image minimale** : Utilisation de `python:3.12-slim`
4. ✅ **Health checks** : Surveillance de l'état de l'application

### Recommandations additionnelles

```bash
# Scanner l'image pour les vulnérabilités
docker scan lighton-workflow-generator

# Limiter les ressources
docker-compose.yml:
  services:
    workflow-generator:
      deploy:
        resources:
          limits:
            cpus: '2'
            memory: 2G
          reservations:
            cpus: '1'
            memory: 512M
```

---

## 📝 Notes

### Compatibilité

- ✅ Linux (Ubuntu, Debian, CentOS, etc.)
- ✅ macOS (Intel et Apple Silicon)
- ✅ Windows (avec Docker Desktop)

### Performance

- **Temps de build initial** : ~3-5 minutes
- **Temps de build avec cache** : ~30 secondes
- **Temps de démarrage** : ~5-10 secondes
- **Utilisation mémoire** : ~300-500 MB

---

## 🆘 Support

### Documentation

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/)

### Problèmes connus

1. **Windows** : Docker Desktop doit être démarré
2. **macOS M1/M2** : L'image est compatible multi-architecture
3. **Linux** : Vérifier que l'utilisateur est dans le groupe `docker`

---

## 📄 Licence

Ce projet est développé par LightOn - Team Use Cases / Workflow Builder.

---

**Version** : 1.1.0
**Date** : 17 janvier 2025
**Auteur** : Nathanaëlle Debaque
**Dernière mise à jour** : Ajout de la configuration Upstash Redis pour persistance serverless
