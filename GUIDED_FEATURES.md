# Guide : Guided Choice & Guided Regex

Ce document explique comment utiliser les fonctionnalités **guided_choice** et **guided_regex** de l'API LightOn Paradigm pour extraire des données structurées de manière fiable.

## 📚 Table des matières

1. [Guided Choice - Classification](#guided-choice---classification)
2. [Guided Regex - Extraction structurée](#guided-regex---extraction-structurée)
3. [Patterns regex prédéfinis](#patterns-regex-prédéfinis)
4. [Exemples de workflows](#exemples-de-workflows)
5. [Meilleures pratiques](#meilleures-pratiques)

---

## 🎯 Guided Choice - Classification

### Qu'est-ce que c'est ?

Le paramètre `guided_choice` force le modèle à choisir **exactement une valeur** parmi une liste prédéfinie. Idéal pour :
- Validation binaire (oui/non, conforme/non conforme)
- Classification en catégories
- Décisions structurées

### Syntaxe

```python
result = await paradigm_client.chat_completion(
    prompt="Votre question",
    guided_choice=["option1", "option2", "option3"]
)
```

### Exemples concrets

#### 1. Validation de conformité

```python
status = await paradigm_client.chat_completion(
    prompt="Le document DC4 est-il conforme au cahier des charges ?",
    guided_choice=["conforme", "non_conforme", "incomplet"]
)
# Retourne exactement : "conforme", "non_conforme" ou "incomplet"
```

#### 2. Classification de sentiment

```python
sentiment = await paradigm_client.chat_completion(
    prompt=f"Classifie ce commentaire client : {commentaire}",
    guided_choice=["positif", "négatif", "neutre"]
)
```

#### 3. Vérification d'égalité

```python
match = await paradigm_client.chat_completion(
    prompt=f"Les valeurs '{valeur1}' et '{valeur2}' sont-elles identiques ?",
    guided_choice=["oui", "non"]
)
```

---

## 🔍 Guided Regex - Extraction structurée

### Qu'est-ce que c'est ?

Le paramètre `guided_regex` force le modèle à générer une sortie qui correspond **exactement** à un pattern regex. Idéal pour :
- SIRET, SIREN, IBAN
- Numéros de téléphone
- Dates, montants
- Tout format strictement défini

### Syntaxe

```python
result = await paradigm_client.chat_completion(
    prompt="Votre question",
    guided_regex=r"votre_pattern_regex"
)
```

### Exemples concrets

#### 1. Extraction de SIRET

```python
siret = await paradigm_client.chat_completion(
    prompt="Extrais le numéro SIRET du document",
    guided_regex=REGEX_SIRET  # r"\\d{14}"
)
# Retourne : "12345678901234"
```

#### 2. Extraction d'IBAN français

```python
iban = await paradigm_client.chat_completion(
    prompt="Extrais l'IBAN du RIB",
    guided_regex=REGEX_IBAN_FR
)
# Retourne : "FR76 1234 5678 9012 3456 7890 123"
```

#### 3. Normalisation de téléphone

```python
phone = await paradigm_client.chat_completion(
    prompt=f"Normalise ce numéro de téléphone : {raw_phone}",
    guided_regex=REGEX_PHONE_FR  # r"\\+33[1-9]\\d{8}"
)
# Retourne : "+33612345678"
```

#### 4. Extraction de montant

```python
montant = await paradigm_client.chat_completion(
    prompt="Quel est le montant TTC ?",
    guided_regex=REGEX_AMOUNT_EUR  # r"\\d{1,10}[.,]\\d{2}"
)
# Retourne : "1234.56"
```

---

## 📋 Patterns Regex Prédéfinis

Les workflows générés incluent automatiquement ces patterns :

### Identifiants français

```python
REGEX_SIRET = r"\\d{14}"                    # 14 chiffres
REGEX_SIREN = r"\\d{9}"                     # 9 chiffres
REGEX_IBAN_FR = r"FR\\d{2}\\s?\\d{4}\\s?\\d{4}\\s?\\d{4}\\s?\\d{4}\\s?\\d{4}\\s?\\d{3}"
```

### Téléphones

```python
REGEX_PHONE_FR = r"\\+33[1-9]\\d{8}"                           # +33612345678
REGEX_PHONE_FR_WITH_SPACES = r"\\+33\\s?[1-9](?:\\s?\\d{2}){4}"  # +33 6 12 34 56 78
```

### Dates

```python
REGEX_DATE_FR = r"\\d{2}/\\d{2}/\\d{4}"     # 25/12/2024
REGEX_DATE_ISO = r"\\d{4}-\\d{2}-\\d{2}"    # 2024-12-25
```

### Montants

```python
REGEX_AMOUNT_EUR = r"\\d{1,10}[.,]\\d{2}"              # 1234.56 ou 1234,56
REGEX_AMOUNT_EUR_WITH_SYMBOL = r"\\d{1,10}[.,]\\d{2}\\s?€"  # 1234.56 €
```

### Email

```python
REGEX_EMAIL = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
```

---

## 💼 Exemples de Workflows

### Workflow 1 : Extraction complète de coordonnées

```python
async def execute_workflow(user_input: str) -> str:
    paradigm_client = ParadigmClient(LIGHTON_API_KEY, LIGHTON_BASE_URL)

    try:
        # Extractions en parallèle avec garantie de format
        siret, phone, email = await asyncio.gather(
            paradigm_client.chat_completion(
                prompt="Extrais le SIRET",
                guided_regex=REGEX_SIRET
            ),
            paradigm_client.chat_completion(
                prompt="Extrais le téléphone",
                guided_regex=REGEX_PHONE_FR
            ),
            paradigm_client.chat_completion(
                prompt="Extrais l'email",
                guided_regex=REGEX_EMAIL
            )
        )

        return f"SIRET: {siret}\nTéléphone: {phone}\nEmail: {email}"

    finally:
        await paradigm_client.close()
```

### Workflow 2 : Validation et extraction conditionnelle

```python
async def execute_workflow(user_input: str) -> str:
    paradigm_client = ParadigmClient(LIGHTON_API_KEY, LIGHTON_BASE_URL)

    try:
        # D'abord, vérifier la conformité
        conformity = await paradigm_client.chat_completion(
            prompt="Le document est-il conforme ?",
            guided_choice=["conforme", "non_conforme", "incomplet"]
        )

        if conformity == "conforme":
            # Si conforme, extraire les données
            siret = await paradigm_client.chat_completion(
                prompt="Extrais le SIRET",
                guided_regex=REGEX_SIRET
            )
            return f"Document conforme - SIRET: {siret}"
        else:
            return f"Document {conformity} - Extraction non effectuée"

    finally:
        await paradigm_client.close()
```

### Workflow 3 : Comparaison de valeurs structurées

```python
async def execute_workflow(user_input: str) -> str:
    paradigm_client = ParadigmClient(LIGHTON_API_KEY, LIGHTON_BASE_URL)

    try:
        # Extraire SIRET de deux documents
        siret_dc4, siret_avis = await asyncio.gather(
            paradigm_client.chat_completion(
                prompt="Extrais le SIRET du DC4",
                guided_regex=REGEX_SIRET
            ),
            paradigm_client.chat_completion(
                prompt="Extrais le SIRET de l'avis d'attribution",
                guided_regex=REGEX_SIRET
            )
        )

        # Comparer avec guided_choice
        match = await paradigm_client.chat_completion(
            prompt=f"Les SIRET {siret_dc4} et {siret_avis} sont-ils identiques ?",
            guided_choice=["oui", "non"]
        )

        if match == "oui":
            return f"✅ SIRET conforme : {siret_dc4}"
        else:
            return f"❌ SIRET différents : DC4={siret_dc4}, Avis={siret_avis}"

    finally:
        await paradigm_client.close()
```

---

## ⚠️ Meilleures Pratiques

### ✅ À FAIRE

1. **Utiliser des regex permissifs**
   ```python
   # ✅ BON : Accepte différents formats
   REGEX_PHONE_FR_WITH_SPACES = r"\\+33\\s?[1-9](?:\\s?\\d{2}){4}"

   # ❌ MAUVAIS : Trop strict
   REGEX_PHONE_STRICT = r"^\\+33[1-9]\\d{8}$"  # Peut bloquer la génération
   ```

2. **Tester les regex avant utilisation**
   ```python
   import re
   test_value = "+33612345678"
   pattern = r"\\+33[1-9]\\d{8}"
   assert re.match(pattern, test_value), "Pattern invalide"
   ```

3. **Combiner guided_choice et guided_regex**
   ```python
   # D'abord vérifier si la donnée existe
   exists = await chat_completion(
       prompt="Y a-t-il un SIRET dans le document ?",
       guided_choice=["oui", "non"]
   )

   # Puis extraire si oui
   if exists == "oui":
       siret = await chat_completion(
           prompt="Extrais le SIRET",
           guided_regex=REGEX_SIRET
       )
   ```

### ❌ À ÉVITER

1. **Regex trop complexes**
   - Peuvent ralentir la génération
   - Risque de blocage si le pattern ne peut être satisfait

2. **Oublier l'échappement**
   ```python
   # ❌ MAUVAIS
   guided_regex=r"\d{14}"  # Simple backslash

   # ✅ BON
   guided_regex=r"\\d{14}"  # Double backslash pour Python dans string
   ```

3. **Utiliser guided_regex pour du texte libre**
   ```python
   # ❌ MAUVAIS : guided_regex n'est pas fait pour ça
   guided_regex=r".*"  # Accepte tout = inutile

   # ✅ BON : Pas de guided_regex pour texte libre
   system_prompt="Réponds en français"  # Utiliser system_prompt à la place
   ```

---

## 📊 Cas d'Usage par Type de Workflow

| Type de Workflow | Fonctionnalité Recommandée | Exemple |
|-----------------|---------------------------|---------|
| Extraction de SIRET/SIREN | `guided_regex` | `REGEX_SIRET` |
| Extraction d'IBAN | `guided_regex` | `REGEX_IBAN_FR` |
| Normalisation téléphone | `guided_regex` | `REGEX_PHONE_FR` |
| Validation conformité | `guided_choice` | `["conforme", "non_conforme"]` |
| Classification documents | `guided_choice` | `["facture", "devis", "bon_commande"]` |
| Comparaison oui/non | `guided_choice` | `["oui", "non"]` |
| Extraction de dates | `guided_regex` | `REGEX_DATE_FR` ou `REGEX_DATE_ISO` |
| Extraction montants | `guided_regex` | `REGEX_AMOUNT_EUR` |

---

## 🔗 Ressources

- [Documentation Paradigm - Structured Output](https://paradigm-academy.lighton.ai/en/dev-guides/ai-models/structured-output#guided-choices)
- [Documentation Paradigm - Regex Templates](https://paradigm-academy.lighton.ai/en/dev-guides/ai-models/regex-templates)
- [Tester vos regex en ligne](https://regex101.com/)

---

**Dernière mise à jour** : 2025-01-08
