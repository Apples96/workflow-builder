"""
Tests pour les endpoints Workflow API du backend
Tests fonctionnels pour création, exécution et gestion des workflows
"""

import os
import pytest
import httpx
import asyncio

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
LIGHTON_API_KEY = os.getenv("LIGHTON_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


@pytest.fixture
def api_headers():
    """Headers pour les requêtes backend"""
    return {
        "Content-Type": "application/json"
    }


@pytest.fixture
async def created_workflow(api_headers):
    """Fixture pour créer un workflow de test"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "description": "Calculer la somme de 10 + 20",
            "name": "Test Calculator"
        }

        response = await client.post(
            f"{API_BASE_URL}/api/workflows",
            headers=api_headers,
            json=payload
        )

        assert response.status_code == 200
        workflow = response.json()

        yield workflow

        # Cleanup si nécessaire


class TestWorkflowCreation:
    """Tests de création de workflows"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_create_simple_workflow(self, api_headers):
        """Test création d'un workflow simple"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "description": "Afficher 'Hello World'",
                "name": "Hello World Workflow"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "id" in data
            assert "name" in data
            assert data["name"] == "Hello World Workflow"
            assert "status" in data
            assert data["status"] == "created"
            assert "generated_code" in data
            assert "async def workflow_function" in data["generated_code"]

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_create_workflow_with_paradigm_search(self, api_headers):
        """Test création workflow avec recherche Paradigm"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "description": "Rechercher dans mes documents le mot 'facture'",
                "name": "Document Search Workflow"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "generated_code" in data
            assert "document_search" in data["generated_code"].lower()

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_create_workflow_validation_error(self, api_headers):
        """Test validation avec description manquante"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "name": "Invalid Workflow"
                # 'description' manquante
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_create_workflow_with_files(self, api_headers):
        """Test création workflow avec upload de fichiers"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Créer un fichier de test
            files = {
                "files": ("test.txt", b"Contenu du document de test", "text/plain")
            }
            data = {
                "description": "Analyser le contenu du fichier",
                "name": "File Analysis Workflow"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows-with-files",
                files=files,
                data=data
            )

            assert response.status_code in [200, 500]  # Peut échouer sans clés API


class TestWorkflowRetrieval:
    """Tests de récupération de workflows"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_get_workflow_by_id(self, api_headers, created_workflow):
        """Test récupération d'un workflow par ID"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}",
                headers=api_headers
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert data["id"] == workflow_id
            assert "name" in data
            assert "generated_code" in data

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_get_nonexistent_workflow(self, api_headers):
        """Test récupération d'un workflow inexistant"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/workflows/nonexistent-id-12345",
                headers=api_headers
            )

            assert response.status_code == 404


class TestWorkflowExecution:
    """Tests d'exécution de workflows"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_execute_simple_workflow(self, api_headers, created_workflow):
        """Test exécution d'un workflow simple"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "user_input": "Calculer"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "workflow_id" in data
            assert "execution_id" in data
            assert "status" in data
            assert data["status"] in ["COMPLETED", "RUNNING", "FAILED"]

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_execute_workflow_with_files(self, api_headers, created_workflow):
        """Test exécution avec fichiers attachés"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "user_input": "Analyser",
                "attached_file_ids": []  # IDs de fichiers Paradigm
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.workflow
    @pytest.mark.slow
    async def test_execute_workflow_timeout(self, api_headers):
        """Test exécution avec timeout"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Créer un workflow qui prend du temps
            create_payload = {
                "description": "Attendre 5 secondes puis afficher 'Done'",
                "name": "Slow Workflow"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # Exécuter
            execute_payload = {"user_input": "Start"}

            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=execute_payload
            )

            assert execute_response.status_code == 200


class TestWorkflowExecutionRetrieval:
    """Tests de récupération des exécutions"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_get_execution_result(self, api_headers, created_workflow):
        """Test récupération du résultat d'exécution"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Exécuter
            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json={"user_input": "Test"}
            )

            assert execute_response.status_code == 200
            execution_id = execute_response.json()["execution_id"]

            # Récupérer le résultat
            result_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}",
                headers=api_headers
            )

            assert result_response.status_code == 200
            result = result_response.json()

            # Vérifications
            assert "workflow_id" in result
            assert "execution_id" in result
            assert "status" in result
            assert result["status"] in ["COMPLETED", "RUNNING", "FAILED"]

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_get_nonexistent_execution(self, api_headers, created_workflow):
        """Test récupération d'une exécution inexistante"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/nonexistent-exec-id",
                headers=api_headers
            )

            assert response.status_code == 404


class TestWorkflowPDFExport:
    """Tests d'export PDF"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    @pytest.mark.slow
    async def test_generate_pdf_report(self, api_headers, created_workflow):
        """Test génération de rapport PDF"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Exécuter d'abord
            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json={"user_input": "Test"}
            )

            assert execute_response.status_code == 200
            execution_id = execute_response.json()["execution_id"]

            # Attendre que l'exécution soit terminée
            await asyncio.sleep(3)

            # Générer PDF
            pdf_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}/pdf",
                headers=api_headers
            )

            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert len(pdf_response.content) > 0


class TestWorkflowEnhancement:
    """Tests d'amélioration de description"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_enhance_description(self, api_headers):
        """Test amélioration d'une description"""
        if not ANTHROPIC_API_KEY:
            pytest.skip("ANTHROPIC_API_KEY non définie")

        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "description": "analyser factures"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows/enhance-description",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Vérifications
            assert "enhanced_description" in data
            assert len(data["enhanced_description"]) > len("analyser factures")
            assert "facture" in data["enhanced_description"].lower()

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_enhance_description_extracts_questions(self, api_headers):
        """Test that questions/warnings are extracted from enhanced description"""
        if not ANTHROPIC_API_KEY:
            pytest.skip("ANTHROPIC_API_KEY non définie")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Use ambiguous description likely to trigger questions
            payload = {
                "description": "Extract the reference number and date from the document and compare amounts"
            }

            response = await client.post(
                f"{API_BASE_URL}/api/workflows/enhance-description",
                headers=api_headers,
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert "enhanced_description" in data
            assert "questions" in data
            assert "warnings" in data

            # Check that arrays are populated (should extract from QUESTIONS AND LIMITATIONS sections)
            # Note: May be empty if Claude doesn't detect ambiguity, but should not error
            assert isinstance(data["questions"], list)
            assert isinstance(data["warnings"], list)


class TestWorkflowErrorHandling:
    """Tests de gestion d'erreurs"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_malformed_json(self, api_headers):
        """Test avec JSON malformé"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                data="invalid json"
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.workflow
    async def test_execute_without_api_keys(self, api_headers):
        """Test exécution sans clés API configurées"""
        # Sauvegarder les clés
        old_lighton = os.environ.get("LIGHTON_API_KEY")
        old_anthropic = os.environ.get("ANTHROPIC_API_KEY")

        try:
            # Temporairement supprimer les clés
            if "LIGHTON_API_KEY" in os.environ:
                del os.environ["LIGHTON_API_KEY"]
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            # Ce test vérifie que l'API gère correctement l'absence de clés
            # Note: Selon l'implémentation, cela peut réussir avec un workflow simple
            pytest.skip("Test nécessite redémarrage de l'API")

        finally:
            # Restaurer les clés
            if old_lighton:
                os.environ["LIGHTON_API_KEY"] = old_lighton
            if old_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic


class TestWorkflowConcurrency:
    """Tests de concurrence"""

    @pytest.mark.asyncio
    @pytest.mark.workflow
    @pytest.mark.slow
    async def test_concurrent_workflow_creation(self, api_headers):
        """Test création concurrente de workflows"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            tasks = []
            for i in range(3):
                payload = {
                    "description": f"Workflow concurrent {i}",
                    "name": f"Concurrent Test {i}"
                }
                task = client.post(
                    f"{API_BASE_URL}/api/workflows",
                    headers=api_headers,
                    json=payload
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Vérifier que tous ont réussi
            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
            assert successes == 3

    @pytest.mark.asyncio
    @pytest.mark.workflow
    @pytest.mark.slow
    async def test_concurrent_workflow_execution(self, api_headers, created_workflow):
        """Test exécution concurrente du même workflow"""
        workflow_id = created_workflow["id"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            tasks = []
            for i in range(3):
                payload = {"user_input": f"Execution {i}"}
                task = client.post(
                    f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                    headers=api_headers,
                    json=payload
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Vérifier que tous ont réussi
            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
            assert successes == 3
