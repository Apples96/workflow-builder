# Analyse Technique du Workflow Generator

**Document d'analyse technique** : [`api/workflow/generator.py`](../api/workflow/generator.py)
**Version** : 1.1.0-mcp
**Date** : Janvier 2025
**Taille** : 3393 lignes de code

---

## 📋 Table des Matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture globale](#2-architecture-globale)
3. [Fonctions utilitaires de post-traitement](#3-fonctions-utilitaires-de-post-traitement)
4. [Classe WorkflowGenerator](#4-classe-workflowgenerator)
5. [Template ParadigmClient intégré](#5-template-paradigmclient-intégré)
6. [Système de prompts massif](#6-système-de-prompts-massif)
7. [Processus de génération et retry](#7-processus-de-génération-et-retry)
8. [Mécanisme d'amélioration des descriptions](#8-mécanisme-damélioration-des-descriptions)
9. [Validation et détection d'erreurs](#9-validation-et-détection-derreurs)
10. [Optimisations et bonnes pratiques](#10-optimisations-et-bonnes-pratiques)
11. [Points critiques et patterns obligatoires](#11-points-critiques-et-patterns-obligatoires)

---

## 1. Vue d'ensemble

Le fichier `generator.py` est le **cœur du système LightOn Workflow Builder**. Il transforme des descriptions en langage naturel en code Python exécutable qui interagit avec l'API Paradigm.

### Statistiques

- **3393 lignes de code** (dont ~2900 lignes de prompts système)
- **2 classes principales** :
  - `WorkflowGenerator` : Génération et orchestration
  - `ParadigmClient` : Template embarqué dans les prompts
- **4 fonctions utilitaires** de post-processing
- **30+ méthodes API Paradigm** documentées dans le template client
- **Retry automatique** avec 3 tentatives maximum
- **Validation syntaxique** avec compilation Python
- **Support multilingue** (détection automatique français/anglais)

### Responsabilités principales

1. **Génération de code Python** à partir de descriptions en langage naturel
2. **Validation et correction automatique** du code généré (retry avec contexte d'erreur)
3. **Amélioration des descriptions utilisateur** avant génération (via Claude)
4. **Intégration complète de l'API Paradigm** dans le code généré
5. **Optimisation des performances** (parallélisation avec `asyncio.gather()`, session HTTP réutilisable)
6. **Post-processing intelligent** (détection de workflow complexes, ajout de staggering)

---

## 2. Architecture globale

### Structure du fichier

```
generator.py
│
├── Imports (lignes 0-8)
│   └── asyncio, logging, re, typing, models, Anthropic, settings
│
├── Fonctions utilitaires (lignes 11-122)
│   ├── detect_workflow_type(description) → str
│   ├── count_api_calls(code) → int
│   ├── fix_fstring_with_braces(code) → str (désactivée)
│   └── add_staggering_to_workflow(code, description) → str
│
├── Classe WorkflowGenerator (lignes 124-3389)
│   ├── __init__()
│   ├── generate_workflow(description, name, context) → Workflow
│   ├── _generate_code(description, context) → str
│   ├── _clean_generated_code(code) → str
│   ├── enhance_workflow_description(raw_description) → Dict
│   └── _validate_code(code) → Dict[str, Any]
│
└── Instance globale (ligne 3392-3393)
    └── workflow_generator = WorkflowGenerator()
```

### Diagramme de flux

```
┌─────────────────────────────────────────────────────────────┐
│                      USER REQUEST                           │
│  "Analyser 5 CV par rapport à une fiche de poste"          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              enhance_workflow_description()                  │
│  • Améliore la description via Claude Sonnet 4              │
│  • Décompose en étapes détaillées (STEP 1, 2, 3...)        │
│  • Détecte ambiguïtés et pose questions                     │
│  • Identifie opportunités de parallélisation                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  generate_workflow()                         │
│  • Crée objet Workflow                                       │
│  • Lance boucle de retry (max 3 tentatives)                 │
│  • Appelle _generate_code()                                  │
│  • Valide avec _validate_code()                              │
│  • Post-processing (staggering si besoin)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    _generate_code()                          │
│  • Envoie description + prompt système (~2900 lignes) à     │
│    Claude Sonnet 4 (claude-sonnet-4-20250514)               │
│  • max_tokens=15000 pour code complet                        │
│  • Nettoie markdown avec _clean_generated_code()             │
│  • Log du code brut et nettoyé                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   _validate_code()                           │
│  • Compile Python (détection SyntaxError)                    │
│  • Vérifie présence de execute_workflow()                    │
│  • Vérifie async def                                          │
│  • Vérifie imports requis (asyncio, aiohttp)                 │
│  • Sauvegarde code échoué dans /tmp si erreur               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                   ┌─────┴──────┐
                   │  Valide ?  │
                   └─────┬──────┘
                         │
            ┌────────────┼────────────┐
            │ OUI                     │ NON
            ▼                         ▼
    ┌──────────────┐         ┌───────────────────┐
    │   SUCCESS    │         │  Retry avec erreur │
    │ Code prêt    │         │  (max 3 fois)      │
    └──────────────┘         └───────────┬────────┘
                                         │
                                         └──────┐
                                                │
                    ┌───────────────────────────┘
                    │
                    ▼
         Ajoute previous_error au context
         Relance _generate_code() avec contexte
```

### Dépendances

```python
# Imports externes
from anthropic import Anthropic  # Appels Claude API
from ..config import settings     # Configuration (API keys)
from .models import Workflow      # Modèle de données workflow

# Bibliothèques standard
import asyncio                    # Programmation asynchrone
import logging                    # Logs
import re                         # Expressions régulières
from typing import Optional, Dict, Any  # Type hints
```

---

## 3. Fonctions utilitaires de post-traitement

Ces fonctions sont appelées **après** la génération initiale du code pour appliquer des optimisations et corrections automatiques.

### 3.1 `detect_workflow_type(description: str) → str`

**Localisation** : Lignes 15-59

**Objectif** : Classifier automatiquement le type de workflow pour choisir les API appropriées.

**Algorithme** :

```python
def detect_workflow_type(description: str) -> str:
    description_lower = description.lower()

    # Mots-clés indiquant extraction de données structurées
    extraction_keywords = [
        'cv', 'resume', 'curriculum vitae', 'curricul',
        'form', 'formulaire', 'application',
        'invoice', 'facture', 'receipt', 'reçu',
        'extract', 'extraire', 'parse', 'parsing',
        'field', 'champ', 'structured', 'structuré',
        'candidat', 'candidate', 'recrutement', 'recruitment',
        'contract', 'contrat',
        'fiche', 'profil', 'profile'
    ]

    # Mots-clés indiquant résumé de documents
    summarization_keywords = [
        'summarize', 'résumer', 'synthèse', 'synthesis',
        'long document', 'rapport', 'report',
        'research paper', 'article', 'white paper',
        'analyse approfondie', 'deep analysis',
        'comprehensive review'
    ]

    # Compte les correspondances
    extraction_score = sum(1 for kw in extraction_keywords if kw in description_lower)
    summarization_score = sum(1 for kw in summarization_keywords if kw in description_lower)

    # Logique de décision
    if extraction_score > 0 and extraction_score > summarization_score:
        return "extraction"
    elif summarization_score > extraction_score:
        return "summarization"
    else:
        # Par défaut : extraction (plus rapide, plus fiable)
        return "extraction"
```

**Utilisation** : Actuellement définit mais pas activement utilisée dans la génération. Peut être utilisée pour des optimisations futures ou des décisions de routing.

---

### 3.2 `count_api_calls(code: str) → int`

**Localisation** : Lignes 61-78

**Objectif** : Compter le nombre d'appels API Paradigm dans le code généré pour détecter les workflows complexes.

**Patterns détectés** :

```python
patterns = [
    r'await\s+paradigm_client\.\w+\(',   # await paradigm_client.method(
    r'paradigm_client\.\w+\([^)]+\)'     # paradigm_client.method(args)
]

total_calls = 0
for pattern in patterns:
    matches = re.findall(pattern, code)
    total_calls += len(matches)

return total_calls
```

**Seuil de déclenchement** : **40 appels API ou plus** → workflow complexe nécessitant staggering

**Utilisation** : Appelé par `add_staggering_to_workflow()` pour détecter workflows complexes.

---

### 3.3 `fix_fstring_with_braces(code: str) → str`

**Localisation** : Lignes 80-87

**Statut** : **DÉSACTIVÉE** (retourne le code inchangé)

```python
def fix_fstring_with_braces(code: str) -> str:
    """
    Désactivée - trop complexe de corriger les f-strings de manière fiable avec regex.
    On compte maintenant sur les instructions améliorées à Claude pour éviter ce problème.
    """
    # Ne fait rien - laisse la validation attraper les erreurs et retry avec contexte
    return code
```

**Raison de désactivation** : Tentatives de correction automatique des f-strings avec regex causaient plus de problèmes qu'elles n'en résolvaient.

**Solution adoptée** : **Instructions strictes à Claude** (lignes 223-230 du prompt système) pour utiliser `.format()` au lieu de f-strings.

---

### 3.4 `add_staggering_to_workflow(code: str, description: str) → str`

**Localisation** : Lignes 89-122

**Objectif** : Ajouter des délais (staggering) entre appels API pour workflows complexes afin d'éviter les surcharges et timeouts.

**Implémentation** :

```python
def add_staggering_to_workflow(code: str, description: str) -> str:
    api_call_count = count_api_calls(code)

    if api_call_count < 40:
        # Pas un workflow complexe, pas besoin de staggering
        return code

    logger.info(f"🔧 Post-processing: Détecté workflow complexe ({api_call_count} appels API)")
    logger.info(f"   Ajout de staggering pour prévenir surcharge API")

    staggering_note = '''
# ⚠️ Note de post-processing: Ce workflow a de nombreux appels API ({})
# Considérez d'ajouter des délais entre groupes d'appels pour éviter les timeouts:
# await asyncio.sleep(2)  # Petit délai entre groupes d'appels API
'''.format(api_call_count)

    # Insère la note après les imports
    if "import asyncio" in code:
        code = code.replace("import asyncio", f"import asyncio{staggering_note}")

    logger.info(f"✅ Post-processing: Ajouté guidance de staggering pour {api_call_count} appels API")

    return code
```

**Seuil de déclenchement** : 40 appels API ou plus

**Note d'implémentation** : Actuellement ajoute un commentaire instructif. Une version future pourrait parser l'AST Python et insérer automatiquement `await asyncio.sleep(2)` entre les blocs de `asyncio.gather()`.

---

## 4. Classe WorkflowGenerator

### 4.1 Initialisation

**Localisation** : Lignes 124-127

```python
class WorkflowGenerator:
    def __init__(self):
        self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
```

**Configuration** :
- **Modèle** : claude-sonnet-4-20250514 (Claude Sonnet 4)
- **API Key** : Chargée depuis `settings.anthropic_api_key`

---

### 4.2 `generate_workflow()` - Méthode principale

**Localisation** : Lignes 128-201

**Signature** :

```python
async def generate_workflow(
    self,
    description: str,
    name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Workflow
```

**Processus complet** (résumé) :

1. **Création workflow** : Objet `Workflow` avec status "generating"
2. **Boucle retry** : Jusqu'à 3 tentatives
3. **Génération** : Appel `_generate_code()` avec description + context
4. **Post-processing** : `fix_fstring_with_braces()` (actuellement no-op)
5. **Validation** : `_validate_code()` vérifie syntaxe et structure
6. **Feedback d'erreur** : Ajoute `previous_error` au context pour retry intelligent
7. **Status final** : "ready" si succès, "failed" si échec après 3 tentatives

**Code du mécanisme de retry** (lignes 152-196) :

```python
# Mécanisme de retry pour génération de code (jusqu'à 3 tentatives)
max_retries = 3
last_error = None

for attempt in range(max_retries):
    try:
        # Génère le code via Anthropic API
        generated_code = await self._generate_code(description, context)

        # Correction f-strings avec accolades AVANT validation
        generated_code = fix_fstring_with_braces(generated_code)

        # Valide le code généré
        validation_result = await self._validate_code(generated_code)

        if validation_result["valid"]:
            # Succès! Code valide
            workflow.generated_code = generated_code
            workflow.update_status("ready")
            return workflow
        else:
            # Validation échouée, prépare pour retry
            last_error = validation_result['error']
            if attempt < max_retries - 1:
                # Ajoute contexte d'erreur pour prochaine tentative
                if context is None:
                    context = {}
                context['previous_error'] = f"Previous attempt had syntax error: {last_error}"
                continue
```

---

### 4.3 `_generate_code()` - Génération via Claude

**Localisation** : Lignes 202-2551

**Signature** :

```python
async def _generate_code(self, description: str, context: Optional[Dict[str, Any]] = None) -> str
```

**Structure** :

1. **Définition du prompt système** (lignes 206-2497) : ~2900 lignes de documentation
2. **Construction du prompt utilisateur** (lignes 2499-2509)
3. **Appel API Anthropic** (lignes 2511-2517)
4. **Extraction et nettoyage du code** (lignes 2519-2534)
5. **Post-processing** (lignes 2536-2547)

**Appel API** :

```python
response = self.anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=15000,  # Augmenté pour génération de code complet
    system=system_prompt,
    messages=[{"role": "user", "content": enhanced_description}]
)

code = response.content[0].text

# Log du code brut pour debugging
logger.info("🔧 RAW GENERATED CODE:")
logger.info("=" * 50)
logger.info(code)
logger.info("=" * 50)

# Nettoie le code - retire formatage markdown si présent
code = self._clean_generated_code(code)
```

**Prompt utilisateur** :

```python
enhanced_description = f"""
Workflow Description: {description}
Additional Context: {context or 'None'}

Generate a complete, self-contained workflow that:
1. Includes all necessary imports and API client classes
2. Implements the execute_workflow function with the exact logic described
3. Can be copy-pasted and run independently on any server
4. Handles the workflow requirements exactly as specified
5. MANDATORY: If the workflow uses documents, implement the if/else pattern for attached_file_ids
"""
```

---

### 4.4 `_clean_generated_code()` - Nettoyage du code

**Localisation** : Lignes 2553-2571

**Objectif** : Retirer le formatage Markdown et assurer structure correcte.

```python
def _clean_generated_code(self, code: str) -> str:
    # Retire blocs de code markdown
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]

    # Retire espaces blancs début/fin
    code = code.strip()

    # Assure que execute_workflow est async
    if "def execute_workflow(" in code and "async def execute_workflow(" not in code:
        code = code.replace("def execute_workflow(", "async def execute_workflow(")

    return code
```

**Corrections appliquées** :

1. Extraction du code depuis blocs markdown (\`\`\`python ... \`\`\`)
2. Suppression espaces blancs
3. Conversion `def execute_workflow` → `async def execute_workflow` si nécessaire

---

### 4.5 `enhance_workflow_description()` - Amélioration IA

**Localisation** : Lignes 2572-3339

**Signature** :

```python
async def enhance_workflow_description(self, raw_description: str) -> Dict[str, Any]
```

**Objectif** : Transformer une description brève utilisateur en spécification détaillée avec étapes claires, détection d'ambiguïtés, et opportunités de parallélisation.

**Retour** :

```python
{
    "enhanced_description": "STEP 1: ...\n---\nSTEP 2: ...",
    "questions": [],  # Maintenant intégrées dans chaque step
    "warnings": []    # Maintenant intégrées dans chaque step
}
```

**Prompt d'amélioration** (lignes 2583-3315) : ~730 lignes d'instructions incluant :

- **Règles de langue** : Préserver la langue originale (français/anglais) exactement
- **APIs disponibles** : Documentation des outils Paradigm avec cas d'usage
- **Parallélisation obligatoire** : Détection automatique d'opérations indépendantes
- **Détection d'ambiguïtés** : Identification de termes vagues ("référence", "date", "montant")
- **Format de sortie** : Structure STEP X + QUESTIONS AND LIMITATIONS
- **Formatage Markdown professionnel** : Séparateurs visuels, hiérarchie, emojis

**Exemple d'amélioration** :

Entrée : `"Analyser 5 CV par rapport à une fiche de poste"`

Sortie :
```
STEP 1: Attendre l'indexation complète de tous les fichiers uploadés (5 CV + 1 fiche de poste)...
QUESTIONS AND LIMITATIONS: None
---
STEP 2a: Extraire les informations du premier CV (CAN RUN IN PARALLEL with 2b, 2c, 2d, 2e)
QUESTIONS AND LIMITATIONS: None
---
STEP 3: Compiler et nettoyer les résultats...
QUESTIONS AND LIMITATIONS: None
```

---

### 4.6 `_validate_code()` - Validation syntaxique

**Localisation** : Lignes 3340-3390

**Implémentation** :

```python
async def _validate_code(self, code: str) -> Dict[str, Any]:
    try:
        # Vérifie erreurs de syntaxe
        compile(code, '<string>', 'exec')

        # Vérifie présence de fonction requise
        if 'def execute_workflow(' not in code:
            return {"valid": False, "error": "Missing execute_workflow function"}

        # Vérifie définition async
        if 'async def execute_workflow(' not in code:
            return {"valid": False, "error": "execute_workflow must be async"}

        # Vérifie imports requis
        required_imports = ['import asyncio', 'import aiohttp']
        for imp in required_imports:
            if imp not in code:
                return {"valid": False, "error": f"Missing required import: {imp}"}

        return {"valid": True, "error": None}

    except SyntaxError as e:
        # Sauvegarde code échoué pour debugging dans /tmp/
        # ...
        return {"valid": False, "error": f"Syntax error: {str(e)}"}
```

**Vérifications effectuées** :

1. **Compilation Python** : `compile(code, '<string>', 'exec')` détecte SyntaxError
2. **Fonction requise** : Présence de `def execute_workflow(`
3. **Définition async** : `async def execute_workflow(`
4. **Imports obligatoires** : `import asyncio`, `import aiohttp`

**Gestion des erreurs** : Si SyntaxError, sauvegarde le code échoué dans `/tmp/workflow_failed_YYYYMMDD_HHMMSS.py`.

---

## 5. Template ParadigmClient intégré

Le template `ParadigmClient` est **embarqué dans le prompt système** (lignes 247-1198) et copié tel quel dans chaque workflow généré.

### Méthodes principales

#### 5.1 Gestion de session (5.55x plus rapide)

```python
async def _get_session(self) -> aiohttp.ClientSession:
    '''
    Réutiliser la même session à travers plusieurs requêtes fournit une amélioration
    de performance 5.55x en évitant l'overhead de setup de connexion sur chaque appel.

    Benchmark officiel (docs Paradigm):
    - Avec réutilisation de session: 1.86s pour 20 requêtes
    - Sans réutilisation de session: 10.33s pour 20 requêtes
    '''
    if self._session is None or self._session.closed:
        self._session = aiohttp.ClientSession()
        logger.debug("🔌 Created new aiohttp session")
    return self._session
```

#### 5.2 `document_search()` - Recherche sémantique

**Signature** :

```python
async def document_search(
    self,
    query: str,
    file_ids: Optional[List[int]] = None,
    workspace_ids: Optional[List[int]] = None,
    chat_session_id: Optional[str] = None,
    model: Optional[str] = None,
    company_scope: bool = False,
    private_scope: bool = True,
    tool: str = "DocumentSearch",
    private: bool = True
) -> Dict[str, Any]
```

**Cas d'usage** :
- Recherche rapide dans workspace
- Extraction d'un champ spécifique depuis fichiers uploadés
- Recherche avec vision OCR (tool="VisionDocumentSearch") pour documents scannés

#### 5.3 `analyze_documents_with_polling()` - Analyse complète

**Performance** : ~20-30 secondes, résultats complets

**Processus** :

1. Démarre l'analyse via `document_analysis_start()`
2. Poll les résultats toutes les 5 secondes
3. Retourne le résultat quand status = "completed"
4. Timeout après 300 secondes (configurable)

**⚠️ CRITIQUE** : JAMAIS en parallèle! Toujours traiter séquentiellement.

#### 5.4 `chat_completion()` - Extraction structurée

**3 modes d'extraction** :

1. **`guided_choice`** : Classification stricte
   ```python
   status = await client.chat_completion(
       prompt="Document conforme ?",
       guided_choice=["conforme", "non_conforme", "incomplet"]
   )
   ```

2. **`guided_regex`** : Formats spécifiques garantis
   ```python
   siret = await client.chat_completion(
       prompt="Extract SIRET",
       guided_regex=r"\d{14}"
   )
   ```

3. **`guided_json`** : JSON valide garanti
   ```python
   data = await client.chat_completion(
       prompt="Extract invoice data",
       guided_json={"type": "object", "properties": {...}}
   )
   ```

#### 5.5 Méthodes additionnelles

- **`upload_file()`** : Upload de fichiers vers Paradigm
- **`get_file()`** : Récupération metadata et status
- **`wait_for_embedding()`** : Attente indexation complète (critique pour PDFs!)
- **`filter_chunks()`** : Filtrage de chunks par pertinence
- **`get_file_chunks()`** : Récupération de tous les chunks
- **`query()`** : Extraction sans génération IA (~30% plus rapide)
- **`analyze_image()`** : Analyse visuelle d'images
- **`delete_file()`** : Suppression de fichiers

---

## 6. Système de prompts massif

### 6.1 Taille et structure du prompt système

**Localisation** : Lignes 206-2497
**Taille** : **~2900 lignes** de documentation et instructions (81% du fichier!)

**Structure principale** :

```
system_prompt = """
├── CRITICAL INSTRUCTIONS (lignes 208-231)
│   ├── Format de sortie (code Python uniquement)
│   ├── Structure requise (async def execute_workflow)
│   ├── Règles de formatage de chaînes (INTERDICTION f-strings)
│   └── Implémentation complète (NO PLACEHOLDERS)
│
├── REQUIRED STRUCTURE (lignes 232-1216)
│   ├── Imports standards
│   ├── Configuration (env variables)
│   └── Template ParadigmClient COMPLET (950 lignes)
│
├── LIBRARY RESTRICTIONS (lignes 1218-1224)
│   └── Uniquement bibliothèques standard Python + aiohttp
│
├── MISSING VALUES DETECTION (lignes 1228-1409)
│   ├── Patterns de valeurs manquantes
│   ├── Fonction is_value_missing()
│   └── Workflow de comparaison correct
│
├── MANDATORY FILE HANDLING CODE (lignes 1410-1589)
│   ├── Vérification attached_file_ids (globals + builtins)
│   ├── Attente embedding avec wait_for_embedding() (MANDATORY!)
│   └── Pattern if/else pour fichiers uploadés vs workspace
│
├── QUERY FORMULATION BEST PRACTICES (lignes 1589-1637)
│   ├── Être spécifique avec noms de champs
│   ├── Inclure formats attendus explicitement
│   └── Utiliser keywords du document réel
│
├── PARALLELIZATION (lignes 1775-1914)
│   ├── Quand paralléliser (document_search, chat_completion)
│   ├── Quand NE PAS paralléliser (analyze_documents_with_polling)
│   └── Exemples corrects vs incorrects
│
├── API RATE LIMITING (lignes 1915-1976)
│   ├── MAX 5 appels par batch
│   └── Délais obligatoires entre batches
│
├── CODE SIMPLICITY PRINCIPLES (lignes 2208-2330)
│   ├── Préférer intelligence API vs code custom
│   ├── Accès robuste aux données (isinstance, .get())
│   └── Minimiser fonctions utilitaires custom
│
└── FINAL INSTRUCTION (ligne 2497)
    └── NO PLACEHOLDER CODE - FULLY IMPLEMENTED
"""
```

### 6.2 Instructions critiques clés

#### Interdiction absolue de f-strings

**Lignes 223-231** :

```
*** CRITICAL STRING FORMATTING RULE - YOU MUST FOLLOW THIS EXACTLY:
    - NEVER EVER use f-strings (f"..." or f'''...''') ANYWHERE in the code
    - ALWAYS use .format() method for ALL string interpolation
    - Example CORRECT: "Bearer {}".format(self.api_key)
    - Example WRONG: f"Bearer {self.api_key}"
    - This prevents ALL syntax errors with curly braces ***
```

**Raison** : Les f-strings avec accolades dans le code généré causent des SyntaxError difficiles à corriger automatiquement.

#### Code implémenté complètement (NO PLACEHOLDERS)

**Lignes 213-217** :

```
5. *** NEVER USE 'pass' OR PLACEHOLDER COMMENTS - IMPLEMENT ALL FUNCTIONS COMPLETELY ***
6. *** EVERY FUNCTION MUST BE FULLY IMPLEMENTED WITH WORKING CODE ***
7. *** NO STUB FUNCTIONS - ALL CODE MUST BE EXECUTABLE AND FUNCTIONAL ***
```

#### Parallélisation obligatoire

**Lignes 216-221** :

```
8. *** ALWAYS USE asyncio.gather() FOR INDEPENDENT PARALLEL TASKS - IMPROVES PERFORMANCE 3-10x ***
   *** CRITICAL: analyze_documents_with_polling() requires BATCH PROCESSING (max 2-3 parallel) ***
   *** Safe to fully parallelize: document_search(), chat_completion(), upload_file() ***
```

#### Pattern obligatoire pour fichiers uploadés

**Lignes 1410-1589** : Code complet de 180 lignes à copier VERBATIM.

**Pattern critique** :

```python
# Check for uploaded files in both globals() and builtins
import builtins
attached_files = None
if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
    attached_files = globals()['attached_file_ids']
elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
    attached_files = builtins.attached_file_ids

if attached_files:
    # User uploaded files - MANDATORY: Wait for embedding FIRST
    file_id = int(attached_files[0])
    try:
        file_info = await paradigm_client.wait_for_embedding(
            file_id=file_id,
            max_wait_time=300,
            poll_interval=2
        )
    except Exception as e:
        await asyncio.sleep(90)  # Fallback wait
else:
    # No uploaded files - search workspace
    search_results = await paradigm_client.document_search(query)
```

**Criticalité** : Ce pattern est **OBLIGATOIRE** - sans lui, workflows échouent avec documents uploadés.

---

## 7. Processus de génération et retry

### 7.1 Flux complet avec retry

```
TENTATIVE 1
└─> _generate_code(description, {})
    └─> Envoie prompt système (~2900 lignes)
        └─> Claude Sonnet 4 génère code
            └─> _clean_generated_code()
                └─> _validate_code()
                    ├─> Valid? → SUCCESS
                    └─> Invalid? → TENTATIVE 2

TENTATIVE 2 (avec contexte d'erreur)
├─> context['previous_error'] = "Previous attempt had syntax error: ..."
└─> _generate_code(description, context)
    └─> Claude reçoit feedback d'erreur
        └─> Génère code corrigé
            └─> _validate_code()
                ├─> Valid? → SUCCESS
                └─> Invalid? → TENTATIVE 3

TENTATIVE 3 (dernière chance)
└─> Si encore échec → Exception levée
    └─> workflow.status = "failed"
```

### 7.2 Mécanisme de retry avec feedback

**Points clés** :

1. **3 tentatives maximum**
2. **Contexte d'erreur** : `context['previous_error']` passé à Claude
3. **Auto-correction** : Claude comprend et corrige ses erreurs
4. **Log des échecs** : Code échoué sauvegardé dans `/tmp/`

**Exemple d'auto-correction** :

Attempt 1 (erreur) :
```python
headers = {"Authorization": f"Bearer {api_key}"}  # ❌ SyntaxError
```

Attempt 2 (corrigé) :
```python
headers = {"Authorization": "Bearer {}".format(api_key)}  # ✅ Correct
```

---

## 8. Mécanisme d'amélioration des descriptions

### 8.1 Objectif

Transformer une description brève en spécification détaillée prête pour génération.

**Entrée** : `"Analyser 5 CV par rapport à une fiche de poste"`

**Sortie** : Décomposition en étapes STEP 1, STEP 2a, STEP 2b, etc. avec détails complets.

### 8.2 Prompt d'amélioration

**Localisation** : Lignes 2583-3315 (~730 lignes)

**Règles critiques** :

1. **Préservation de la langue** : JAMAIS traduire (français reste français, anglais reste anglais)
2. **Parallélisation obligatoire** : Détecter automatiquement opérations indépendantes
3. **Détection d'ambiguïtés** : Poser questions pour "référence", "date", "montant", etc.
4. **Format de sortie** : PLAIN TEXT (pas JSON!) avec structure STEP + QUESTIONS
5. **Markdown professionnel** : Séparateurs visuels (%%%), emojis, hiérarchie claire

**Exemple de question générée** :

```
QUESTIONS AND LIMITATIONS:
⚠️ AMBIGUITY DETECTED - Clarification needed:

1. **"numéro de référence"** is ambiguous:
   - Do you mean the procedure number (e.g., 22U012)?
   - Do you mean the market number (e.g., 617529)?
   - In which section of each document?
   - What format (numeric, alphanumeric)?
```

---

## 9. Validation et détection d'erreurs

### 9.1 Vérifications de compilation

```python
async def _validate_code(self, code: str) -> Dict[str, Any]:
    try:
        # 1. Vérifie erreurs de syntaxe
        compile(code, '<string>', 'exec')

        # 2. Vérifie présence execute_workflow()
        if 'def execute_workflow(' not in code:
            return {"valid": False, "error": "Missing execute_workflow function"}

        # 3. Vérifie définition async
        if 'async def execute_workflow(' not in code:
            return {"valid": False, "error": "execute_workflow must be async"}

        # 4. Vérifie imports requis
        required_imports = ['import asyncio', 'import aiohttp']
        for imp in required_imports:
            if imp not in code:
                return {"valid": False, "error": f"Missing required import: {imp}"}

        return {"valid": True, "error": None}

    except SyntaxError as e:
        # Sauvegarde code échoué dans /tmp/
        return {"valid": False, "error": f"Syntax error: {str(e)}"}
```

### 9.2 Sauvegarde des codes échoués

**Chemin** : `/tmp/workflow_failed_YYYYMMDD_HHMMSS.py` (Unix) ou équivalent Windows

**Avantage** : Permet debugging manuel des échecs de génération.

---

## 10. Optimisations et bonnes pratiques

### 10.1 Session HTTP réutilisable (5.55x plus rapide)

**Benchmark officiel Paradigm** :
- Sans réutilisation : 10.33s pour 20 requêtes
- Avec réutilisation : **1.86s pour 20 requêtes** (5.55x)

**Implémentation** :

```python
async def _get_session(self) -> aiohttp.ClientSession:
    if self._session is None or self._session.closed:
        self._session = aiohttp.ClientSession()
    return self._session
```

### 10.2 Parallélisation avec asyncio.gather()

**Performance** : 3-10x amélioration

**Exemple** :

```python
# Sequential: 3 tasks × 5s = 15s total
result1 = await task1()
result2 = await task2()
result3 = await task3()

# Parallel: max(5, 5, 5) = 5s total (3x faster!)
result1, result2, result3 = await asyncio.gather(task1(), task2(), task3())
```

### 10.3 Batching API (max 5 appels par batch)

**Pattern correct** :

```python
# Batch 1: First 5 queries
batch1_tasks = [paradigm_client.document_search(q) for q in queries[:5]]
batch1_results = await asyncio.gather(*batch1_tasks)
await asyncio.sleep(0.5)  # MANDATORY DELAY

# Batch 2: Next 5 queries
batch2_tasks = [paradigm_client.document_search(q) for q in queries[5:10]]
batch2_results = await asyncio.gather(*batch2_tasks)
await asyncio.sleep(0.5)  # MANDATORY DELAY

all_results = batch1_results + batch2_results
```

**Règles** :
1. MAX 5 appels parallèles par batch
2. `asyncio.sleep(0.5)` entre batches (standard ops)
3. `asyncio.sleep(1)` entre batches (heavy ops: VisionDocumentSearch, upload)

### 10.4 Accès robuste aux données (isinstance, .get())

**Pattern défensif** :

```python
# ✅ CORRECT - Type checking avant accès
if isinstance(results, dict):
    documents = results.get('documents', [])
elif isinstance(results, list):
    documents = results
else:
    documents = []

for doc in documents:
    if isinstance(doc, dict):
        doc_id = doc.get('id', 'unknown')
        doc_name = doc.get('filename', 'Document {}'.format(doc_id))
```

**Principe** : Toujours vérifier types avec `isinstance()` et utiliser `.get()` avec defaults.

---

## 11. Points critiques et patterns obligatoires

### 11.1 Pattern fichiers uploadés (MANDATORY)

**Localisation prompt** : Lignes 1410-1589 (180 lignes)

**Code obligatoire** :

```python
import builtins
attached_files = None
if 'attached_file_ids' in globals() and globals()['attached_file_ids']:
    attached_files = globals()['attached_file_ids']
elif hasattr(builtins, 'attached_file_ids') and builtins.attached_file_ids:
    attached_files = builtins.attached_file_ids

if attached_files:
    # MANDATORY: Wait for embedding!
    file_id = int(attached_files[0])
    file_info = await paradigm_client.wait_for_embedding(file_id=file_id, max_wait_time=300)
    # Then use the file...
else:
    # Search workspace
    search_results = await paradigm_client.document_search(query)
```

**Pourquoi obligatoire** : PDFs nécessitent 30-120s traitement OCR. Sans attente → erreur "document not found".

---

### 11.2 Interdiction analyze_documents_with_polling() en parallèle

**Règle critique** :

```
❌ WRONG: await asyncio.gather(*[analyze_documents_with_polling(...) for doc in docs])
✅ CORRECT: for doc in docs: result = await analyze_documents_with_polling(...)
```

**Raison** : Endpoint lourd (deep analysis) → timeouts si parallélisé.

---

### 11.3 Scopes critiques pour file_ids

**Règle** :

```python
# ✅ CORRECT: Target specific file only
content = await document_search(query, file_ids=[doc_id], company_scope=False, private_scope=False)

# ❌ WRONG: Returns ALL private collection + specified file!
content = await document_search(query, file_ids=[doc_id])
```

**Explication** : Par défaut, `document_search()` cherche dans toute la collection privée même si `file_ids` spécifié.

---

### 11.4 Préservation mapping file_id → résultat

**Problème** : Lors traitement multiples fichiers en parallèle, perte du mapping.

**Solution** : Stocker tuples `(file_id, task)` :

```python
# ✅ CORRECT
file_search_tasks = []
for file_id in attached_files:
    task = paradigm_client.document_search(query, file_ids=[int(file_id)])
    file_search_tasks.append((file_id, task))  # Keep mapping!

file_search_results = []
for i in range(0, len(file_search_tasks), 5):
    batch = file_search_tasks[i:i+5]
    batch_tasks = [task for file_id, task in batch]
    batch_results = await asyncio.gather(*batch_tasks)
    for j, result in enumerate(batch_results):
        file_id = batch[j][0]  # Get file_id from tuple
        file_search_results.append((file_id, result))
```

---

### 11.5 Détection valeurs manquantes avant comparaison

**Problème** : API retourne "Non trouvé" → comparaison de 2 "Non trouvé" = faux positif.

**Solution** : Fonction `is_value_missing()` + vérification avant comparaison :

```python
def is_value_missing(value: str) -> bool:
    if not value or not value.strip():
        return True
    missing_indicators = ["non trouvé", "not found", "no information", ...]
    value_lower = value.lower()
    return any(indicator in value_lower for indicator in missing_indicators)

# Check for missing BEFORE comparison
raw_value_dc4 = step_search_dc4.get("answer", "")
raw_value_avis = step_search_avis.get("answer", "")

dc4_missing = is_value_missing(raw_value_dc4)
avis_missing = is_value_missing(raw_value_avis)

if dc4_missing or avis_missing:
    status = "ATTENTION Donnees manquantes"
else:
    # Both values exist, now compare
    comparison = await chat_completion("Compare...")
    status = "OK Conforme" if "identique" in comparison.lower() else "ERREUR Non conforme"
```

**Principe clé** : Vérifier `is_value_missing()` sur valeurs brutes AVANT normalisation/comparaison.

---

## Conclusion

Le `generator.py` est un système sophistiqué avec les caractéristiques suivantes :

### Métriques

- **3393 lignes** de code total
- **~2900 lignes** de prompts système (81% du fichier)
- **950 lignes** de template ParadigmClient
- **730 lignes** de prompt d'amélioration
- **30+ méthodes API** Paradigm documentées
- **Retry 3x** avec contexte d'erreur
- **Performance 5.55x** avec session réutilisable
- **Performance 3-10x** avec parallélisation

### Points forts

- ✅ Retry automatique avec auto-correction
- ✅ Client Paradigm complet et optimisé intégré
- ✅ Prompt système très détaillé pour qualité de code
- ✅ Post-processing pour workflows complexes
- ✅ Support extraction structurée (guided_*)
- ✅ Patterns obligatoires documentés précisément

### Points d'amélioration

- 🔄 Validation sémantique plus poussée
- 🔄 Staggering automatique (parser AST)
- 🔄 Modularisation du prompt système
- 🔄 Tests unitaires automatiques du code généré

---

**Document maintenu par** : LightOn Workflow Builder Team
**Dernière mise à jour** : 24 janvier 2025
**Basé sur** : Lecture complète de `api/workflow/generator.py` (3393 lignes)
