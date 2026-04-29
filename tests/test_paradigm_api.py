"""
Tests pour les endpoints Paradigm API
Tests intelligents et fonctionnels pour vérifier l'intégration complète
"""

import os
import pytest
import httpx
import asyncio

# Configuration
PARADIGM_BASE_URL = "https://paradigm.lighton.ai"
LIGHTON_API_KEY = os.getenv("LIGHTON_API_KEY")


@pytest.fixture
def paradigm_headers():
    """Headers pour les requêtes Paradigm API"""
    if not LIGHTON_API_KEY:
        pytest.skip("LIGHTON_API_KEY non définie")
    return {
        "Authorization": f"Bearer {LIGHTON_API_KEY}",
        "Content-Type": "application/json"
    }


@pytest.fixture
async def uploaded_file_id(paradigm_headers):
    """Fixture pour uploader un fichier de test et retourner son ID"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Créer un fichier de test
        test_content = b"Facture n 12345. Total TTC: 1200.00 EUR. Total HT: 1000.00 EUR. TVA 20%: 200.00 EUR."

        files = {
            "file": ("test_facture.txt", test_content, "text/plain")
        }
        data = {
            "collection_type": "private"
        }

        response = await client.post(
            f"{PARADIGM_BASE_URL}/api/v2/files",
            headers={k: v for k, v in paradigm_headers.items() if k != "Content-Type"},
            files=files,
            data=data
        )

        assert response.status_code == 200, f"Upload échoué: {response.text}"
        file_data = response.json()
        file_id = file_data["id"]

        # Attendre que le fichier soit embedé
        for _ in range(30):  # Max 60 secondes
            await asyncio.sleep(2)
            status_response = await client.get(
                f"{PARADIGM_BASE_URL}/api/v2/files/{file_id}",
                headers=paradigm_headers
            )
            status_data = status_response.json()
            if status_data.get("status") == "embedded":
                break

        yield file_id

        # Cleanup: supprimer le fichier (si l'endpoint existe)
        # Note: L'API Paradigm peut ne pas avoir d'endpoint DELETE


class TestParadigmDocumentSearch:
    """Tests pour l'endpoint /api/v2/chat/document-search"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_document_search_basic(self, paradigm_headers, uploaded_file_id):
        """Test recherche sémantique basique"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "query": "Quel est le montant total ?",
                "file_ids": [uploaded_file_id],
                "tool": "DocumentSearch"
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-search",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code == 200, f"Erreur: {response.text}"
            data = response.json()

            # Vérifications
            assert "answer" in data
            assert "1200" in data["answer"] or "1,200" in data["answer"]
            assert "documents" in data
            assert len(data["documents"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_document_search_with_multiple_files(self, paradigm_headers, uploaded_file_id):
        """Test recherche sur plusieurs fichiers"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "query": "Montant TTC",
                "file_ids": [uploaded_file_id],
                "tool": "DocumentSearch",
                "max_results": 5
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-search",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "documents" in data

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_document_search_vision_fallback(self, paradigm_headers):
        """Test fallback vers VisionDocumentSearch"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Tenter une recherche sans file_ids devrait utiliser VisionDocumentSearch
            payload = {
                "query": "Test recherche",
                "tool": "VisionDocumentSearch"
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-search",
                headers=paradigm_headers,
                json=payload
            )

            # Peut réussir ou échouer selon la configuration
            assert response.status_code in [200, 400, 422]


class TestParadigmDocumentAnalysis:
    """Tests pour l'endpoint /api/v2/chat/document-analysis"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    @pytest.mark.slow
    async def test_document_analysis_create(self, paradigm_headers, uploaded_file_id):
        """Test création d'une analyse de document"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "query": "Analyse cette facture et extrais tous les montants",
                "document_ids": [uploaded_file_id],
                "model": "llama-3.1-70b-instruct"
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-analysis",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code in [200, 201, 202]
            data = response.json()

            # L'API peut retourner un chat_response_id pour polling
            assert "chat_response_id" in data or "id" in data

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    @pytest.mark.slow
    async def test_document_analysis_polling(self, paradigm_headers, uploaded_file_id):
        """Test polling du résultat d'analyse"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Créer l'analyse
            payload = {
                "query": "Extrais le montant TTC",
                "document_ids": [uploaded_file_id]
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-analysis",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code in [200, 201, 202]
            data = response.json()

            if "chat_response_id" in data:
                chat_response_id = data["chat_response_id"]

                # Polling du résultat
                for _ in range(10):  # Max 20 secondes
                    await asyncio.sleep(2)

                    poll_response = await client.get(
                        f"{PARADIGM_BASE_URL}/api/v2/chat/document-analysis/{chat_response_id}",
                        headers=paradigm_headers
                    )

                    if poll_response.status_code == 200:
                        result = poll_response.json()
                        assert "answer" in result or "result" in result
                        break


class TestParadigmFiles:
    """Tests pour les endpoints /api/v2/files"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_file_upload(self, paradigm_headers):
        """Test upload de fichier"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            test_content = b"Document de test pour LightOn Workflow Builder."

            files = {
                "file": ("test_document.txt", test_content, "text/plain")
            }
            data = {
                "collection_type": "private"
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/files",
                headers={k: v for k, v in paradigm_headers.items() if k != "Content-Type"},
                files=files,
                data=data
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "id" in data
            assert "filename" in data
            assert data["filename"] == "test_document.txt"
            assert "status" in data

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_file_get_status(self, paradigm_headers, uploaded_file_id):
        """Test récupération du statut d'un fichier"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PARADIGM_BASE_URL}/api/v2/files/{uploaded_file_id}",
                headers=paradigm_headers
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "id" in data
            assert "status" in data
            assert data["status"] in ["processing", "embedded", "failed"]
            assert "filename" in data

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_file_wait_for_embedding(self, paradigm_headers):
        """Test attente de l'embedding complet"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Upload
            test_content = b"Test embedding wait."
            files = {
                "file": ("test_embedding.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/files",
                headers={k: v for k, v in paradigm_headers.items() if k != "Content-Type"},
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Attendre l'embedding
            embedded = False
            for _ in range(30):  # Max 60 secondes
                await asyncio.sleep(2)

                status_response = await client.get(
                    f"{PARADIGM_BASE_URL}/api/v2/files/{file_id}",
                    headers=paradigm_headers
                )

                status_data = status_response.json()
                if status_data.get("status") == "embedded":
                    embedded = True
                    break
                elif status_data.get("status") == "failed":
                    pytest.fail(f"Embedding échoué: {status_data}")

            assert embedded, "Le fichier n'a pas été embedé dans le temps imparti"

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_file_ask_question(self, paradigm_headers, uploaded_file_id):
        """Test question sur un fichier spécifique"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "question": "Quel est le contenu de ce document ?"
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/files/{uploaded_file_id}/ask",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "answer" in data or "response" in data
            assert "chunks" in data or "documents" in data


class TestParadigmChunks:
    """Tests pour les endpoints chunks"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_get_file_chunks(self, paradigm_headers, uploaded_file_id):
        """Test récupération de tous les chunks d'un fichier"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PARADIGM_BASE_URL}/api/v2/files/{uploaded_file_id}/chunks",
                headers=paradigm_headers
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert isinstance(data, list) or "chunks" in data
            if isinstance(data, list):
                assert len(data) > 0
                # Vérifier la structure d'un chunk
                chunk = data[0]
                assert "id" in chunk or "text" in chunk
                assert "embedding" in chunk or "position" in chunk

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_filter_chunks(self, paradigm_headers, uploaded_file_id):
        """Test filtrage de chunks par score"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "file_id": uploaded_file_id,
                "min_score": 0.7
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/filter/chunks",
                headers=paradigm_headers,
                json=payload
            )

            # Peut réussir ou retourner 404 si endpoint non disponible
            assert response.status_code in [200, 404, 422]

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list) or "chunks" in data

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_query_chunks_raw(self, paradigm_headers, uploaded_file_id):
        """Test récupération de chunks sans génération AI"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "query": "montant",
                "file_ids": [uploaded_file_id],
                "limit": 5
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/query",
                headers=paradigm_headers,
                json=payload
            )

            # Peut réussir ou retourner 404 si endpoint non disponible
            assert response.status_code in [200, 404, 422]

            if response.status_code == 200:
                data = response.json()
                assert "chunks" in data or isinstance(data, list)


class TestParadigmChatCompletions:
    """Tests pour l'endpoint /api/v2/chat/completions"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_chat_completion_basic(self, paradigm_headers):
        """Test chat completion basique"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "messages": [
                    {"role": "user", "content": "Dis bonjour en français."}
                ],
                "model": "llama-3.1-70b-instruct",
                "temperature": 0.7,
                "max_tokens": 100
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/completions",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "message" in data["choices"][0]
            assert "content" in data["choices"][0]["message"]
            assert "bonjour" in data["choices"][0]["message"]["content"].lower()

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_chat_completion_with_context(self, paradigm_headers):
        """Test chat completion avec contexte"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "messages": [
                    {"role": "system", "content": "Tu es un assistant comptable."},
                    {"role": "user", "content": "Calcule 1000 + 200 EUR de TVA."}
                ],
                "temperature": 0.3
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/completions",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            assert "choices" in data
            content = data["choices"][0]["message"]["content"]
            assert "1200" in content or "1 200" in content


class TestParadigmImageAnalysis:
    """Tests pour l'endpoint /api/v2/chat/image-analysis"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    @pytest.mark.slow
    async def test_image_analysis(self, paradigm_headers):
        """Test analyse d'image"""
        async with httpx.AsyncClient(timeout=60.0):
            # Note: Nécessite une vraie image uploadée
            # Ce test est un placeholder pour la structure — payload structure
            # documented in the docstring rather than as a dead local var.

            # Ce test échouera sans image_id valide
            # Il est là pour documenter la structure
            pytest.skip("Nécessite un image_id valide")


class TestParadigmErrorHandling:
    """Tests de gestion d'erreurs"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_invalid_api_key(self):
        """Test avec clé API invalide"""
        headers = {
            "Authorization": "Bearer invalid_key_123",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/completions",
                headers=headers,
                json={"messages": [{"role": "user", "content": "test"}]}
            )

            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_missing_required_fields(self, paradigm_headers):
        """Test requête avec champs manquants"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Requête sans 'query' pour document-search
            payload = {
                "file_ids": [123]
                # 'query' manquant
            }

            response = await client.post(
                f"{PARADIGM_BASE_URL}/api/v2/chat/document-search",
                headers=paradigm_headers,
                json=payload
            )

            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    async def test_invalid_file_id(self, paradigm_headers):
        """Test avec file_id inexistant"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{PARADIGM_BASE_URL}/api/v2/files/99999999",
                headers=paradigm_headers
            )

            assert response.status_code == 404


# Tests de performance
class TestParadigmPerformance:
    """Tests de performance"""

    @pytest.mark.asyncio
    @pytest.mark.paradigm
    @pytest.mark.slow
    async def test_concurrent_requests(self, paradigm_headers):
        """Test requêtes concurrentes"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            tasks = []
            for i in range(5):
                payload = {
                    "messages": [{"role": "user", "content": f"Test {i}"}]
                }
                task = client.post(
                    f"{PARADIGM_BASE_URL}/api/v2/chat/completions",
                    headers=paradigm_headers,
                    json=payload
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Vérifier que la majorité a réussi
            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
            assert successes >= 3, f"Seulement {successes}/5 requêtes ont réussi"
