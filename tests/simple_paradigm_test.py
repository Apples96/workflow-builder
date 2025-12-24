#!/usr/bin/env python3
"""
Test simple pour vérifier si l'API Paradigm fonctionne
Teste l'endpoint de chat completion (le plus basique)
"""

import os
import httpx

PARADIGM_BASE_URL = "https://paradigm.lighton.ai"
LIGHTON_API_KEY = os.getenv("LIGHTON_API_KEY")

if not LIGHTON_API_KEY:
    print("❌ LIGHTON_API_KEY non définie")
    print("Exporter avec: export LIGHTON_API_KEY=sk-...")
    exit(1)

print(f"🔑 API Key trouvée: {LIGHTON_API_KEY[:10]}...")
print(f"🌐 Test de l'API: {PARADIGM_BASE_URL}")
print()

# Test 1: Chat Completion (le plus simple)
print("📝 Test 1: Chat Completion")
print("-" * 50)

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{PARADIGM_BASE_URL}/api/v2/chat/completions",
            headers={
                "Authorization": f"Bearer {LIGHTON_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "alfred-4.2",
                "messages": [
                    {"role": "user", "content": "Dis bonjour en une phrase"}
                ],
                "max_tokens": 50
            }
        )

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Succès!")
            print(f"Réponse: {data['choices'][0]['message']['content'][:100]}")
        else:
            print(f"❌ Erreur HTTP {response.status_code}")
            print(f"Réponse: {response.text[:500]}")

except Exception as e:
    print(f"❌ Exception: {e}")

print()
print("=" * 50)
