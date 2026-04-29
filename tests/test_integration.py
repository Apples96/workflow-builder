"""
Tests d'intégration end-to-end
Scénarios complets utilisant plusieurs endpoints
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
    """Headers pour les requêtes"""
    return {
        "Content-Type": "application/json"
    }


class TestFullWorkflowCycle:
    """Tests du cycle complet de workflow"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_create_and_execute_workflow(self, api_headers):
        """Test: Créer un workflow, l'exécuter et récupérer le résultat"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            # Étape 1: Créer le workflow
            create_payload = {
                "description": "Calculer la somme de deux nombres: 42 + 58",
                "name": "Addition Workflow"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow = create_response.json()
            workflow_id = workflow["id"]

            # Étape 2: Exécuter le workflow
            execute_payload = {
                "user_input": "Calculer"
            }

            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=execute_payload
            )

            assert execute_response.status_code == 200
            execution = execute_response.json()
            execution_id = execution["execution_id"]

            # Étape 3: Attendre et récupérer le résultat
            await asyncio.sleep(3)

            result_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}",
                headers=api_headers
            )

            assert result_response.status_code == 200
            result = result_response.json()

            # Vérifications
            assert result["status"] == "COMPLETED"
            assert "100" in str(result.get("result", ""))

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_workflow_with_pdf_export(self, api_headers):
        """Test: Workflow complet avec export PDF"""
        async with httpx.AsyncClient(timeout=180.0) as client:
            # Créer workflow
            create_payload = {
                "description": "Lister les nombres de 1 à 5",
                "name": "Number List Workflow"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # Exécuter
            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json={"user_input": "Lister"}
            )

            assert execute_response.status_code == 200
            execution_id = execute_response.json()["execution_id"]

            # Attendre
            await asyncio.sleep(3)

            # Générer PDF
            pdf_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}/pdf",
                headers=api_headers
            )

            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert len(pdf_response.content) > 1000  # PDF non vide


class TestFileToWorkflowIntegration:
    """Tests d'intégration fichiers -> workflows"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_upload_file_and_create_workflow(self, api_headers):
        """Test: Upload fichier puis créer workflow qui l'utilise"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=180.0) as client:
            # Étape 1: Upload fichier
            test_content = b"Invoice #123: Total amount 5000 EUR"
            files = {
                "file": ("invoice.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Attendre l'embedding
            for _ in range(30):
                await asyncio.sleep(2)
                status_response = await client.get(
                    f"{API_BASE_URL}/api/files/{file_id}",
                    headers=api_headers
                )
                if status_response.json().get("status") == "embedded":
                    break

            # Étape 2: Créer workflow utilisant le fichier
            create_payload = {
                "description": f"Rechercher dans le document {file_id} le montant total",
                "name": "Document Search Workflow"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # Étape 3: Exécuter le workflow
            execute_payload = {
                "user_input": "Chercher le montant",
                "attached_file_ids": [file_id]
            }

            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=execute_payload
            )

            assert execute_response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_upload_and_query_file(self, api_headers):
        """Test: Upload fichier et poser plusieurs questions"""
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=180.0) as client:
            # Upload
            test_content = b"Project Report 2025. Budget: 100000 EUR. Team: 5 persons. Duration: 12 months."
            files = {
                "file": ("report.txt", test_content, "text/plain")
            }
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Attendre embedding
            for _ in range(30):
                await asyncio.sleep(2)
                status_response = await client.get(
                    f"{API_BASE_URL}/api/files/{file_id}",
                    headers=api_headers
                )
                if status_response.json().get("status") == "embedded":
                    break

            # Poser plusieurs questions
            questions = [
                "Quel est le budget ?",
                "Combien de personnes dans l'équipe ?",
                "Quelle est la durée du projet ?"
            ]

            for question in questions:
                payload = {"question": question}
                response = await client.post(
                    f"{API_BASE_URL}/api/files/{file_id}/ask",
                    headers=api_headers,
                    json=payload
                )

                assert response.status_code == 200
                answer = response.json().get("answer", "")

                # Vérifications spécifiques par question
                if "budget" in question.lower():
                    assert "100000" in answer or "100 000" in answer
                elif "personnes" in question.lower() or "équipe" in question.lower():
                    assert "5" in answer
                elif "durée" in question.lower():
                    assert "12" in answer


class TestEnhanceAndExecute:
    """Tests amélioration de description puis exécution"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_enhance_then_create_workflow(self, api_headers):
        """Test: Améliorer description puis créer workflow"""
        if not ANTHROPIC_API_KEY:
            pytest.skip("ANTHROPIC_API_KEY non définie")

        async with httpx.AsyncClient(timeout=180.0) as client:
            # Étape 1: Améliorer la description
            enhance_payload = {
                "description": "calculer taxes"
            }

            enhance_response = await client.post(
                f"{API_BASE_URL}/api/workflows/enhance-description",
                headers=api_headers,
                json=enhance_payload
            )

            assert enhance_response.status_code == 200
            enhanced_desc = enhance_response.json()["enhanced_description"]

            # Étape 2: Créer workflow avec description améliorée
            create_payload = {
                "description": enhanced_desc,
                "name": "Tax Calculator"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # Étape 3: Exécuter
            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json={"user_input": "Calculer"}
            )

            assert execute_response.status_code == 200


class TestMultipleWorkflowsParallel:
    """Tests d'exécution parallèle de workflows"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_create_and_execute_multiple_workflows(self, api_headers):
        """Test: Créer et exécuter plusieurs workflows en parallèle"""
        async with httpx.AsyncClient(timeout=300.0) as client:
            workflows_data = [
                {"description": "Calculer 10 + 10", "name": "Add 10"},
                {"description": "Calculer 20 + 20", "name": "Add 20"},
                {"description": "Calculer 30 + 30", "name": "Add 30"}
            ]

            # Créer workflows en parallèle
            create_tasks = []
            for data in workflows_data:
                task = client.post(
                    f"{API_BASE_URL}/api/workflows",
                    headers=api_headers,
                    json=data
                )
                create_tasks.append(task)

            create_responses = await asyncio.gather(*create_tasks)

            assert all(r.status_code == 200 for r in create_responses)
            workflow_ids = [r.json()["id"] for r in create_responses]

            # Exécuter tous en parallèle
            execute_tasks = []
            for workflow_id in workflow_ids:
                task = client.post(
                    f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                    headers=api_headers,
                    json={"user_input": "Calculate"}
                )
                execute_tasks.append(task)

            execute_responses = await asyncio.gather(*execute_tasks)

            assert all(r.status_code == 200 for r in execute_responses)


class TestErrorRecovery:
    """Tests de récupération d'erreurs"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute_invalid_workflow(self, api_headers):
        """Test: Exécuter un workflow invalide et récupérer"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Essayer d'exécuter un workflow inexistant
            response = await client.post(
                f"{API_BASE_URL}/api/workflows/invalid-id-12345/execute",
                headers=api_headers,
                json={"user_input": "Test"}
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_workflow_failure_handling(self, api_headers):
        """Test: Gérer l'échec d'exécution d'un workflow"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Créer un workflow qui pourrait échouer
            create_payload = {
                "description": "Diviser 10 par 0",  # Erreur mathématique
                "name": "Error Workflow"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # Exécuter
            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json={"user_input": "Execute"}
            )

            # Peut réussir (si l'IA génère du code safe) ou échouer
            assert execute_response.status_code in [200, 500]


class TestHealthAndStatus:
    """Tests de santé et statut de l'API"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_check(self):
        """Test: Vérifier le health check de l'API"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")

            assert response.status_code == 200
            data = response.json()

            assert "status" in data
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_frontend_serving(self):
        """Test: Vérifier que le frontend est servi"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE_URL}/")

            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")


class TestCompleteUserJourney:
    """Tests du parcours utilisateur complet"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_complete_document_analysis_journey(self, api_headers):
        """
        Test: Parcours complet
        1. Upload un document
        2. Créer un workflow d'analyse
        3. Exécuter le workflow avec le document
        4. Récupérer le résultat
        5. Exporter en PDF
        """
        if not LIGHTON_API_KEY:
            pytest.skip("LIGHTON_API_KEY non définie")

        async with httpx.AsyncClient(timeout=300.0) as client:
            # 1. Upload document
            document_content = b"""
            INVOICE #INV-2025-001
            Date: 2025-12-02
            Customer: Acme Corp

            Items:
            - Product A: 1000 EUR
            - Product B: 500 EUR
            - Shipping: 50 EUR

            Subtotal: 1550 EUR
            VAT (20%): 310 EUR
            Total: 1860 EUR
            """

            files = {"file": ("invoice_001.txt", document_content, "text/plain")}
            data = {"collection_type": "private"}

            upload_response = await client.post(
                f"{API_BASE_URL}/api/files/upload",
                files=files,
                data=data
            )

            assert upload_response.status_code == 200
            file_id = upload_response.json()["id"]

            # Attendre embedding
            for _ in range(30):
                await asyncio.sleep(2)
                status_response = await client.get(
                    f"{API_BASE_URL}/api/files/{file_id}",
                    headers=api_headers
                )
                if status_response.json().get("status") == "embedded":
                    break

            # 2. Créer workflow d'analyse
            create_payload = {
                "description": "Analyser une facture et extraire le montant total, le numéro de facture et les items",
                "name": "Invoice Analyzer"
            }

            create_response = await client.post(
                f"{API_BASE_URL}/api/workflows",
                headers=api_headers,
                json=create_payload
            )

            assert create_response.status_code == 200
            workflow_id = create_response.json()["id"]

            # 3. Exécuter avec le document
            execute_payload = {
                "user_input": "Analyser la facture",
                "attached_file_ids": [file_id]
            }

            execute_response = await client.post(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/execute",
                headers=api_headers,
                json=execute_payload
            )

            assert execute_response.status_code == 200
            execution_id = execute_response.json()["execution_id"]

            # 4. Récupérer résultat
            await asyncio.sleep(5)

            result_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}",
                headers=api_headers
            )

            assert result_response.status_code == 200

            # 5. Exporter en PDF
            pdf_response = await client.get(
                f"{API_BASE_URL}/api/workflows/{workflow_id}/executions/{execution_id}/pdf",
                headers=api_headers
            )

            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert len(pdf_response.content) > 1000
