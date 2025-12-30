# 🚀 Architecture du Workflow Runner - Application Standalone

Documentation complète pour générer des applications standalone à partir de workflows.

---

## 🎯 L'idée en une phrase simple

**Au lieu de juste générer du code Python, on va générer une APPLICATION COMPLÈTE (site web + serveur) que le client peut installer chez lui.**

---

## 📚 Analogie simple : La recette de cuisine

### Aujourd'hui (ce que tu fais déjà)

```
Tech LightOn → Crée une RECETTE (code Python)
              ↓
Client → Reçoit juste la recette
       → Doit avoir sa propre cuisine (serveur)
       → Doit savoir cuisiner (coder)
       → Doit acheter les ingrédients (bibliothèques)
```

**Problème** : Le client doit être développeur pour utiliser la recette !

---

### Demain (ce qu'on va faire)

```
Tech LightOn → Crée un PLAT TOUT PRÊT dans une boîte (application complète)
              ↓
Client → Reçoit la boîte
       → Ouvre la boîte
       → Réchauffe au micro-ondes (lance Docker)
       → Mange ! (utilise l'application)
```

**Avantage** : Le client n'a PAS besoin d'être développeur !

---

## 🔍 Explication détaillée étape par étape

### PARTIE 1 : Ce que fait le tech LightOn (dans le Workflow Builder)

#### Étape 1 : Créer le workflow (comme maintenant)

Le tech va sur ton Workflow Builder et tape :
```
"Vérifier les documents administratifs : DC4, Acte d'engagement, RIB"
```

Claude génère automatiquement le **code Python** :
```python
async def execute_workflow(user_input: str, file_ids: list[str]) -> str:
    # Analyser le DC4
    dc4_result = await paradigm_client.analyze_documents(...)
    # Analyser l'Acte
    acte_result = await paradigm_client.analyze_documents(...)
    # Analyser le RIB
    rib_result = await paradigm_client.analyze_documents(...)
    return "Résultats..."
```

**C'est ce qui existe déjà aujourd'hui.**

---

#### Étape 2 : Cliquer sur "Générer l'application complète" (NOUVEAU)

Le tech clique sur un **nouveau bouton** : **"📦 Générer l'app complète"**

**Ce qui se passe en coulisses** :

1. **Claude analyse le code Python** et se pose des questions :
   - "Combien de fichiers ce workflow a besoin ?"
   - "Quels sont les noms de ces fichiers ?"
   - "Est-ce qu'il faut un champ de texte ?"

2. **Claude génère une configuration** (un fichier JSON) :
   ```json
   {
     "workflow_name": "Vérification administrative",
     "files": [
       { "label": "DC4", "required": true },
       { "label": "Acte d'engagement", "required": true },
       { "label": "RIB", "required": true }
     ]
   }
   ```

3. **Le serveur crée un package complet** avec :
   - **Frontend** : Site web avec formulaire adapté
   - **Backend** : Serveur qui exécute le code Python
   - **Config Docker** : Pour lancer facilement
   - **Documentation** : Instructions en français

4. **Le tech télécharge un fichier ZIP** : `workflow-verification-administrative.zip`

---

### PARTIE 2 : Ce que fait le client (installation)

#### Étape 1 : Décompresser le ZIP

Le client reçoit un fichier ZIP. Il le décompresse et voit :

```
workflow-verification-administrative/
├── frontend/           ← Site web (HTML/CSS/JavaScript)
├── backend/            ← Serveur (Python)
├── docker-compose.yml  ← Fichier pour lancer facilement
└── README.md           ← Mode d'emploi en français
```

**C'est comme recevoir un logiciel à installer.**

---

#### Étape 2 : Configurer la clé API

Le client ouvre un fichier `.env` et met sa clé API Paradigm :
```
PARADIGM_API_KEY=sa-cle-secrete-ici
```

**Analogie** : C'est comme entrer le mot de passe Wi-Fi pour se connecter.

---

#### Étape 3 : Lancer l'application

Le client ouvre un terminal et tape **UNE SEULE commande** :
```bash
docker-compose up -d
```

**Ce qui se passe** :
- Docker lance le serveur automatiquement
- Le site web est accessible sur `http://localhost:3000`

**Analogie** : C'est comme appuyer sur le bouton "Power" d'un ordinateur.

---

#### Étape 4 : Utiliser l'application

Le client ouvre son navigateur et va sur `http://localhost:3000`

Il voit **une interface adaptée automatiquement** :

```
┌──────────────────────────────────────────────┐
│  Vérification administrative                 │
├──────────────────────────────────────────────┤
│                                              │
│  📄 DC4 *                                    │
│  [Cliquez ou glissez-déposez]               │
│                                              │
│  📄 Acte d'engagement *                      │
│  [Cliquez ou glissez-déposez]               │
│                                              │
│  📄 RIB *                                    │
│  [Cliquez ou glissez-déposez]               │
│                                              │
│  [✓ Vérifier les documents]                 │
└──────────────────────────────────────────────┘
```

Le client :
1. **Glisse ses 3 fichiers PDF** dans les zones
2. **Clique sur "Vérifier"**
3. **Voit les résultats** à l'écran
4. **Télécharge le PDF** avec les résultats

**Analogie** : C'est comme utiliser un site web normal (Amazon, Gmail, etc.)

---

## 🤔 Pourquoi c'est génial ?

### Pour le client
- ✅ **Pas besoin d'être développeur** : Il utilise juste un site web
- ✅ **Installation facile** : Une seule commande
- ✅ **Interface adaptée** : Pas besoin de comprendre le code
- ✅ **Hébergement chez lui** : Il contrôle tout (sécurité)

### Pour LightOn
- ✅ **Livraison rapide** : Génération automatique en quelques secondes
- ✅ **Personnalisé** : Chaque client a une interface adaptée à son workflow
- ✅ **Pas de support technique** : Le client est autonome
- ✅ **Scalable** : Fonctionne pour n'importe quel workflow

---

## 📦 Qu'est-ce qu'il y a dans le package ?

### 1. Frontend (Site web)

**Fichiers** :
- `index.html` : La page web
- `styles.css` : Le design (couleurs, polices, etc.)
- `app.js` : Le code JavaScript (interactions)
- `config.json` : La configuration de l'interface

**Ce que ça fait** :
- Affiche un formulaire adapté (selon le workflow)
- Permet de glisser-déposer des fichiers
- Envoie les données au serveur
- Affiche les résultats
- Génère le PDF

**Analogie** : C'est la **vitrine** du magasin que le client voit.

---

### 2. Backend (Serveur)

**Fichiers** :
- `main.py` : Le serveur qui reçoit les requêtes
- `workflow.py` : Le code du workflow (généré par Claude)
- `paradigm_client.py` : Le client pour appeler l'API Paradigm
- `requirements.txt` : La liste des bibliothèques nécessaires

**Ce que ça fait** :
- Reçoit les fichiers uploadés par le client
- Envoie les fichiers à Paradigm
- Exécute le workflow
- Retourne les résultats au frontend

**Analogie** : C'est la **cuisine** du restaurant (invisible pour le client).

---

### 3. Docker (Container)

**Fichiers** :
- `docker-compose.yml` : Configuration Docker
- `Dockerfile` : Instructions pour créer le container

**Ce que ça fait** :
- Lance le serveur automatiquement
- Installe toutes les dépendances
- Configure l'environnement

**Analogie** : C'est le **four micro-ondes** qui réchauffe le plat tout prêt.

---

### 4. Documentation

**Fichiers** :
- `README.md` : Mode d'emploi en français
- `.env.example` : Exemple de configuration

**Ce que ça fait** :
- Explique comment installer
- Explique comment utiliser
- Liste les variables d'environnement

**Analogie** : C'est le **manuel d'utilisation** du produit.

---

## 🎨 Comment l'interface est adaptée automatiquement ?

### Exemple 1 : Workflow UGAP (6 fichiers)

**Code du workflow** :
```python
# Besoin de 6 fichiers différents
dc4 = analyze(file_ids[0])
acte = analyze(file_ids[1])
avis = analyze(file_ids[2])
declaration = analyze(file_ids[3])
rib = analyze(file_ids[4])
dc4_initial = analyze(file_ids[5])
```

**Claude détecte** : "Ce workflow a besoin de 6 fichiers avec des noms spécifiques"

**Interface générée** :
```
┌──────────────────────┐
│  📄 DC4             │
│  📄 Acte            │
│  📄 Avis            │
│  📄 Déclaration     │
│  📄 RIB             │
│  📄 DC4 initial     │
│  [Vérifier]         │
└──────────────────────┘
```

**6 zones de glisser-déposer** ! ✅

---

### Exemple 2 : Workflow simple (1 fichier + texte)

**Code du workflow** :
```python
# Besoin d'un fichier et d'un texte
result = analyze(user_input, file_ids[0])
```

**Claude détecte** : "Ce workflow a besoin d'un champ texte et d'un fichier"

**Interface générée** :
```
┌──────────────────────────────────┐
│  Que cherchez-vous ?             │
│  [___________________________]   │
│                                  │
│  📄 Document à analyser          │
│  [Glissez votre fichier]        │
│                                  │
│  [Analyser]                      │
└──────────────────────────────────┘
```

**1 champ texte + 1 zone fichier** ! ✅

---

### Exemple 3 : Workflow texte seulement (pas de fichier)

**Code du workflow** :
```python
# Besoin seulement d'un texte
result = chat_completion(user_input)
```

**Claude détecte** : "Ce workflow a seulement besoin d'un texte"

**Interface générée** :
```
┌──────────────────────────────────┐
│  Entrez votre texte :            │
│  [___________________________]   │
│  [___________________________]   │
│  [___________________________]   │
│                                  │
│  [Analyser]                      │
└──────────────────────────────────┘
```

**Juste un grand champ texte** ! ✅

---

## 🔄 Le processus complet (récapitulatif visuel)

```
TECH LIGHTON                           CLIENT
    │                                      │
    │ 1. Crée workflow                    │
    │    "Vérifier DC4 + RIB"             │
    │                                      │
    │ 2. Clique "Générer app"             │
    │    ↓                                 │
    │    Claude analyse le code            │
    │    Claude génère l'interface         │
    │    Serveur crée le ZIP               │
    │                                      │
    │ 3. Télécharge                        │
    │    workflow-verification.zip         │
    │                                      │
    │ 4. Envoie au client ────────────────→│
    │                                      │
    │                                      │ 5. Décompresse le ZIP
    │                                      │
    │                                      │ 6. Configure .env
    │                                      │    (clé API)
    │                                      │
    │                                      │ 7. Lance Docker
    │                                      │    docker-compose up
    │                                      │
    │                                      │ 8. Ouvre navigateur
    │                                      │    localhost:3000
    │                                      │
    │                                      │ 9. Upload fichiers
    │                                      │
    │                                      │ 10. Voit résultats
    │                                      │
    │                                      │ 11. Télécharge PDF
```

---

## 🏗️ Architecture technique détaillée

### Workflow d'analyse du code par Claude

#### Prompt pour Claude

```
Analyze this Python workflow code and extract the user interface requirements.

Workflow Code:
```python
{workflow_code}
```

Based on the code above, generate a JSON configuration describing the required user interface.

Output format:
{
  "workflow_name": "Short descriptive name",
  "workflow_description": "Brief description of what this workflow does",
  "requires_text_input": true/false,
  "text_input_label": "Label for text input (if required)",
  "text_input_placeholder": "Placeholder text",
  "requires_files": true/false,
  "files": [
    {
      "key": "variable_name_in_code",
      "label": "User-friendly name",
      "description": "What this file is for",
      "required": true/false,
      "accept": ".pdf,.docx,.txt"
    }
  ]
}

Guidelines:
1. Look for function parameters like `user_input`, `query`, `text`
2. Look for file-related code like `file_ids`, `document_ids`, `analyze_documents`
3. Infer file names from API calls (e.g., "Extraire le SIRET du DC4" → file labeled "DC4")
4. Count how many different files are needed
5. Determine if files are required or optional
6. Be user-friendly: use French labels if the code is in French context
```

---

### Structure du package généré

```
workflow-{nom}/
├── frontend/
│   ├── index.html              # Page principale
│   ├── styles.css              # Styles CSS
│   ├── app.js                  # Logique JavaScript
│   └── config.json             # Configuration UI (générée par Claude)
│
├── backend/
│   ├── main.py                 # API FastAPI
│   ├── workflow.py             # Code du workflow (généré)
│   ├── paradigm_client.py      # Client Paradigm API
│   └── requirements.txt        # Dépendances Python
│
├── docker-compose.yml          # Configuration Docker
├── Dockerfile                  # Image Docker
├── .env.example                # Variables d'environnement
├── vercel.json                 # Config Vercel (optionnel)
└── README.md                   # Documentation en français
```

---

### Backend API Endpoint

```python
# api/main.py

@app.post("/api/workflows/{workflow_id}/generate-app")
async def generate_standalone_app(workflow_id: str, request: Request):
    """
    Génère une application standalone complète pour le workflow.
    Retourne un fichier ZIP contenant frontend + backend.
    """
    data = await request.json()
    workflow_code = data['workflow_code']
    workflow_name = data['workflow_name']

    # 1. Analyser le code avec Claude pour générer la config UI
    ui_config = await analyze_workflow_for_ui(workflow_code)

    # 2. Générer les fichiers du package
    package = WorkflowPackageGenerator(
        workflow_name=workflow_name,
        workflow_code=workflow_code,
        ui_config=ui_config
    )

    # 3. Créer le ZIP
    zip_buffer = package.generate_zip()

    # 4. Retourner le ZIP
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=workflow-{workflow_name}.zip"
        }
    )
```

---

### Frontend - Génération dynamique d'interface

```javascript
// app.js

class DynamicUIGenerator {

    async loadWorkflow() {
        // 1. Charger la config UI
        const response = await fetch('config.json');
        const config = await response.json();

        // 2. Générer l'interface
        this.renderUI(config);
    }

    renderUI(config) {
        const container = document.getElementById('workflow-interface');

        // Titre et description
        container.innerHTML = `
            <div class="workflow-header">
                <h2>${config.workflow_name}</h2>
                <p>${config.workflow_description}</p>
            </div>
        `;

        // Input texte (si nécessaire)
        if (config.requires_text_input) {
            container.innerHTML += `
                <div class="text-input-section">
                    <label>${config.text_input_label}</label>
                    <textarea
                        id="user-input"
                        placeholder="${config.text_input_placeholder}"
                        rows="5"
                    ></textarea>
                </div>
            `;
        }

        // Fichiers (si nécessaire)
        if (config.requires_files) {
            const filesHTML = config.files.map((file, index) => `
                <div class="file-upload-box ${file.required ? 'required' : 'optional'}">
                    <div class="upload-icon">☁️</div>
                    <label>
                        ${file.label}
                        ${file.required ? '<span class="required-mark">*</span>' : ''}
                    </label>
                    <p class="file-description">${file.description}</p>
                    <input
                        type="file"
                        id="file-${index}"
                        data-key="${file.key}"
                        accept="${file.accept}"
                        ${file.required ? 'required' : ''}
                    />
                    <div class="file-name" id="filename-${index}"></div>
                </div>
            `).join('');

            container.innerHTML += `
                <div class="files-section">
                    <h3>Documents requis</h3>
                    <div class="file-upload-grid">
                        ${filesHTML}
                    </div>
                </div>
            `;
        }

        // Bouton d'exécution
        container.innerHTML += `
            <button class="btn-execute" onclick="executeWorkflow()">
                ✓ ${config.requires_files ? 'Vérifier les informations' : 'Analyser'}
            </button>
        `;

        // Initialiser les événements (drag & drop)
        this.initializeDragDrop();
    }

    initializeDragDrop() {
        document.querySelectorAll('.file-upload-box').forEach(box => {
            const input = box.querySelector('input[type="file"]');

            // Drag & drop
            box.addEventListener('dragover', (e) => {
                e.preventDefault();
                box.classList.add('drag-over');
            });

            box.addEventListener('drop', (e) => {
                e.preventDefault();
                box.classList.remove('drag-over');
                input.files = e.dataTransfer.files;
                this.showFileName(input);
            });

            // Click to upload
            box.addEventListener('click', () => input.click());
            input.addEventListener('change', () => this.showFileName(input));
        });
    }
}
```

---

## ❓ Questions fréquentes

### Q1 : Le client doit savoir coder ?
**R : NON !** Il utilise juste un site web normal. C'est comme utiliser Gmail.

### Q2 : Le client doit installer des choses ?
**R : Juste Docker** (un logiciel gratuit). C'est comme installer Chrome ou Firefox.

### Q3 : L'interface est toujours la même ?
**R : NON !** Claude adapte l'interface selon le workflow. Chaque client a une interface personnalisée.

### Q4 : Le client peut modifier l'interface ?
**R : OUI !** Il peut changer les couleurs, les textes, etc. dans les fichiers CSS/HTML.

### Q5 : Le client dépend de LightOn ?
**R : NON !** Il héberge tout chez lui. LightOn n'intervient plus après la livraison.

### Q6 : Comment Claude sait combien de fichiers le workflow nécessite ?
**R :** Claude analyse le code Python :
- Compte les appels à `analyze_documents_with_polling`
- Regarde les indices dans `file_ids[0]`, `file_ids[1]`, etc.
- Lit les descriptions dans les requêtes ("Extraire le SIRET du DC4" → fichier "DC4")

### Q7 : Que se passe-t-il si le workflow change après génération ?
**R :** Il faut régénérer le package complet. Le client reçoit un nouveau ZIP et redéploie.

### Q8 : Le PDF est généré comment ?
**R :** Avec jsPDF côté client (dans le navigateur), comme on a implémenté dans le Workflow Builder.

---

## 🚀 Prochaines étapes d'implémentation

### Phase 1 : Prototype (MVP)
1. Ajouter le bouton "📦 Générer l'app complète" dans le Workflow Builder
2. Implémenter l'endpoint `/api/workflows/{id}/generate-app`
3. Créer le `WorkflowPackageGenerator` basique
4. Tester avec un workflow simple (1-2 fichiers)

### Phase 2 : Génération intelligente
1. Implémenter l'analyse du code par Claude
2. Générer la config UI automatiquement
3. Adapter le frontend dynamiquement
4. Tester avec workflows complexes (UGAP, etc.)

### Phase 3 : Finalisation
1. Ajouter les templates CSS professionnels
2. Générer la documentation README complète
3. Tester le déploiement Docker et Vercel
4. Créer des exemples de packages

### Phase 4 : Production
1. Intégrer avec le repo de Milo (quand disponible)
2. Tests avec vrais workflows clients
3. Déploiement sur environnements de production
4. Documentation utilisateur finale

---

## 📚 Références

- **Code senior (ugap-dc4)** : Exemple d'application similaire pour les contrôles DC4
- **jsPDF** : Génération de PDF côté client (déjà implémenté dans v1.6.0)
- **FastAPI** : Framework backend Python
- **Docker** : Containerisation pour déploiement simplifié

---

**Version** : 1.0
**Date de création** : 20/11/2025
**Auteur** : Documentation pour le Workflow Builder - LightOn
