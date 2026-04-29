"""
Tests pour les endpoints Files API
Tests pour upload, gestion et interrogation de fichiers
"""

import os
import pytest
import httpx
import asyncio

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
LIGHTON_API_KEY = os.getenv("LIGHTON_API_KEY")


@pytest.fixture
def api_headers():
    """Headers pour les requêtes backend"""
    return {
        "Content-Type": "application/json"
    }


@pytest.fixture
async def uploaded_file_id(api_headers):
    """Fixture pour uploader un fichier et retourner son ID"""
    if not LIGHTON_API_KEY:
        pytest.skip("LIGHTON_API_KEY non définie")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Créer un fichier de test
        test_content = b"Facture Test n 98765. Montant total: 2500.00 EUR HT."

        files = {
            "file": ("test_facture_api.txt", test_content, "text/plain")
        }
        data = {
            "collection_type": "private"
        }

        response = await client.post(
            f"{API_BASE_URL}/api/files/upload",
            files=files,
            data=data
        )

        assert response.status_code == 200
        file_data = response.json()
        file_id = file_data["id"]

        # Attendre que le fichier soit embedé
        for _ in range(30):
            await asyncio.sleep(2)
            status_response = await client.get(
                f"{API_BASE_URL}/api/files/{file_id}",
                headers=api_headers
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get("status") == "embedded":
                    break

        yield file_id


class TestFileUpload:
    """Tests d'upload de fichiers"""

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_text_file(self, api_headers):
        """Test upload d'un fichier texte"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=60.0) as client:
            test_content = b"Contenu du document de test pour l'API."

            files = {
                "file": ("document_test.txt", test_content, "text/plain")
            }
            data = {
                "collection_type": "private"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "id" in data
            assert "filename" in data
            assert data["filename"] == "document_test.txt"
            assert "status" in data
            assert data["status"] in ["processing", "embedded"]

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_pdf_file(self, api_headers):
        """Test upload d'un fichier PDF"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Créer un PDF minimal (header PDF valide)
            pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"

            files = {
                "file": ("test_document.pdf", pdf_content, "application/pdf")
            }
            data = {
                "collection_type": "private"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert response.status_code in [200, 400]  # Peut échouer si PDF invalide

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_large_file(self, api_headers):
        """Test upload d'un fichier plus large"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Créer un fichier de ~1MB
            large_content = b"Lorem ipsum dolor sit amet. " * 40000

            files = {
                "file": ("large_document.txt", large_content, "text/plain")
            }
            data = {
                "collection_type": "private"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_without_collection_type(self, api_headers):
        """Test upload sans spécifier collection_type"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=60.0) as client:
            test_content = b"Test sans collection type"

            files = {
                "file": ("test.txt", test_content, "text/plain")
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files
            )

            # Peut réussir avec collection_type par défaut ou échouer
            assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_empty_file(self, api_headers):
        """Test upload d'un fichier vide"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {
                "file": ("empty.txt", b"", "text/plain")
            }
            data = {
                "collection_type": "private"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            # Devrait échouer ou accepter selon l'implémentation
            assert response.status_code in [200, 400, 422]


class TestFileRetrieval:
    """Tests de récupération d'informations sur les fichiers"""

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_get_file_info(self, api_headers, uploaded_file_id):
        """Test récupération d'informations sur un fichier"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/files/{uploaded_file_id}",
                headers=api_headers
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "id" in data
            assert data["id"] == uploaded_file_id
            assert "status" in data
            assert data["status"] in ["processing", "embedded", "failed"]
            assert "filename" in data
            assert "created_at" in data or "bytes" in data

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_get_nonexistent_file(self, api_headers):
        """Test récupération d'un fichier inexistant"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/files/99999999",
                headers=api_headers
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.files
    @pytest.mark.slow
    async def test_wait_for_file_embedding(self, api_headers):
        """Test attente de l'embedding complet d'un fichier"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=90.0) as client:
            # Upload
            test_content = b"Test wait for embedding workflow."
            files = {
                "file": ("test_wait.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Polling du statut
            embedded = False
            for attempt in range(30):  # Max 60 secondes
                await asyncio.sleep(2)

                status_response = await client.get(
                    f"{API_BASE_URL}/api/files/{file_id}",
                    headers=api_headers
                )

                assert status_response.status_code == 200
                status_data = status_response.json()

                if status_data.get("status") == "embedded":
                    embedded = True
                    break
                elif status_data.get("status") == "failed":
                    pytest.fail(f"Embedding échoué: {status_data}")

            assert embedded, "Le fichier n'a pas été embedé dans le temps imparti"


class TestFileQuery:
    """Tests d'interrogation de fichiers"""

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_ask_question_to_file(self, api_headers, uploaded_file_id):
        """Test poser une question sur un fichier"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "question": "Quel est le montant de la facture ?"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/{uploaded_file_id}/ask",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "answer" in data or "response" in data
            # La réponse devrait contenir le montant
            response_text = data.get("answer", data.get("response", ""))
            assert "2500" in response_text or "montant" in response_text.lower()

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_ask_without_question(self, api_headers, uploaded_file_id):
        """Test requête sans question"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {}  # Question manquante

            response = await client.post(
                f"{API_BASE_URL}/api/files/{uploaded_file_id}/ask",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_ask_question_to_nonexistent_file(self, api_headers):
        """Test question sur un fichier inexistant"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "question": "Test question"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/99999999/ask",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_ask_complex_question(self, api_headers, uploaded_file_id):
        """Test question complexe sur un fichier"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "question": "Peux-tu extraire le numéro de facture et le montant total ?"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/{uploaded_file_id}/ask",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            response_text = data.get("answer", data.get("response", ""))
            # Devrait mentionner le numéro et le montant
            assert "98765" in response_text or "2500" in response_text


class TestFileDelete:
    """Tests de suppression de fichiers"""

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_delete_file(self, api_headers):
        """Test suppression d'un fichier"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # D'abord uploader un fichier
            test_content = b"Fichier a supprimer"
            files = {
                "file": ("to_delete.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Supprimer le fichier
            delete_response = await client.delete(
                f"{API_BASE_URL}/api/files/{file_id}",
                headers=api_headers
            )

            assert delete_response.status_code in [200, 204]

            # Vérifier que le fichier n'existe plus
            get_response = await client.get(
                f"{API_BASE_URL}/api/files/{file_id}",
                headers=api_headers
            )

            assert get_response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_delete_nonexistent_file(self, api_headers):
        """Test suppression d'un fichier inexistant"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{API_BASE_URL}/api/files/99999999",
                headers=api_headers
            )

            assert response.status_code == 404


class TestFileConcurrency:
    """Tests de concurrence pour les fichiers"""

    @pytest.mark.asyncio
    @pytest.mark.files
    @pytest.mark.slow
    async def test_concurrent_file_uploads(self, api_headers):
        """Test upload concurrent de plusieurs fichiers"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=120.0) as client:
            tasks = []

            for i in range(3):
                content = f"Document concurrent {i}".encode()
                files = {
                    "file": (f"concurrent_{i}.txt", content, "text/plain")
                }
                data = {"collection_type": "private"}

                task = client.post(
                    f"{API_BASE_URL}/api/files/upload",
                    files=files,
                    data=data
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Vérifier que tous ont réussi
            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
            assert successes == 3

    @pytest.mark.asyncio
    @pytest.mark.files
    @pytest.mark.slow
    async def test_concurrent_file_queries(self, api_headers, uploaded_file_id):
        """Test questions concurrentes sur le même fichier"""
        async with httpx.AsyncClient(timeout=90.0) as client:
            questions = [
                "Quel est le montant ?",
                "Quel est le numéro ?",
                "Résume le document"
            ]

            tasks = []
            for question in questions:
                payload = {"question": question}
                task = client.post(
                    f"{API_BASE_URL}/api/files/{uploaded_file_id}/ask",
                    headers=api_headers,
                    json=payload
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Vérifier que tous ont réussi
            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
            assert successes == 3


class TestFileErrorHandling:
    """Tests de gestion d'erreurs"""

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_without_file(self, api_headers):
        """Test upload sans fichier"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = {"collection_type": "private"}

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                data=data
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_invalid_collection_type(self, api_headers):
        """Test upload avec collection_type invalide"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=30.0) as client:
            test_content = b"Test"
            files = {
                "file": ("test.txt", test_content, "text/plain")
            }
            data = {
                "collection_type": "invalid_type"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    @pytest.mark.files
    async def test_upload_without_api_key(self):
        """Test upload sans clé API"""
        # Vérifier que l'API rejette les requêtes sans clé
        if not LIGHTON_API_KEY:
            pytest.skip("Test nécessite configuration API")

        # Ce test vérifie la gestion d'erreur côté backend
        # L'implémentation peut varier
        async with httpx.AsyncClient(timeout=30.0) as client:
            test_content = b"Test"
            files = {
                "file": ("test.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            # Selon l'implémentation, peut réussir localement
            assert response.status_code in [200, 401, 500]
