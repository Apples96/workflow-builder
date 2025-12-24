# Tests - LightOn Workflow Builder

Complete test suite for Paradigm API endpoints and backend API.

## 📋 Overview

This test suite covers:
- ✅ **11 Paradigm API endpoints** (document-search, document-analysis, files, chunks, etc.)
- ✅ **Backend endpoints** (workflows, execution, files, PDF export)
- ✅ **End-to-end integration tests**
- ✅ **Sandbox security tests**
- ✅ **Performance and concurrency tests**

## 🚀 Quick Start

```bash
# Install dependencies
make install

# Verify environment variables
make verify-env

# Run all tests
make test

# Quick tests only
make test-quick
```

## 📦 Structure

```
tests/
├── Makefile                    # Test commands
├── conftest.py                 # Pytest configuration
├── test_paradigm_api.py        # Paradigm endpoint tests (11 endpoints)
├── test_workflow_api.py        # Workflow tests (creation, execution)
├── test_files_api.py           # File tests (upload, query)
├── test_integration.py         # End-to-end tests
├── test_security.py            # Sandbox security tests
└── README.md                   # This file
```

## 🔧 Configuration

### Required Environment Variables

Create a `.env` file at the project root:

```bash
# API Keys
LIGHTON_API_KEY=your_lighton_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# URLs (optional)
API_BASE_URL=http://localhost:8000
PARADIGM_BASE_URL=https://paradigm.lighton.ai
```

### Installation

```bash
# Install pytest and dependencies
make install

# Verify configuration
make verify-env

# Check that backend API responds
make check-api
```

## 🧪 Test Commands

### General Tests

```bash
make test              # All tests with coverage
make test-quick        # Quick tests only (without slow)
make test-smoke        # Quick API health check
make test-verbose      # Tests in very verbose mode
make test-failed       # Rerun only failed tests
```

### Tests by Category

```bash
make test-paradigm     # Paradigm API endpoint tests
make test-workflow     # Workflow creation/execution tests
make test-files        # File upload/management tests
make test-integration  # End-to-end scenario tests
make test-security     # Sandbox security tests
```

### Coverage and Reports

```bash
make test-coverage     # Generate HTML coverage report
make report            # Display last test summary
```

### API Management

```bash
make start-api         # Start backend API
make stop-api          # Stop backend API
make check-api         # Check if API responds
make logs-api          # Display API logs
```

### Complete Workflow

```bash
make full-test         # Complete cycle: start API → test → stop
make ci-test           # Tests for CI/CD (without starting API)
```

### Utilities

```bash
make clean             # Clean test files
make help              # Display help
```

## 📊 Paradigm API Tests

### Tested Endpoints (11/11)

| Endpoint | Tests | Status |
|----------|-------|--------|
| `POST /api/v2/chat/document-search` | 3 tests | ✅ |
| `POST /api/v2/chat/document-analysis` | 2 tests | ✅ |
| `POST /api/v2/chat/completions` | 2 tests | ✅ |
| `POST /api/v2/files` | 5 tests | ✅ |
| `GET /api/v2/files/{id}` | 3 tests | ✅ |
| `POST /api/v2/files/{id}/ask` | 4 tests | ✅ |
| `GET /api/v2/files/{id}/chunks` | 1 test | ✅ |
| `POST /api/v2/filter/chunks` | 1 test | ✅ |
| `POST /api/v2/query` | 1 test | ✅ |
| `POST /api/v2/chat/image-analysis` | 1 test | ✅ |
| Error handling | 3 tests | ✅ |

**Total: 26 tests for Paradigm API**

### Paradigm Test Examples

```bash
# Test semantic search
pytest tests/test_paradigm_api.py::TestParadigmDocumentSearch::test_document_search_basic -v

# Test file upload
pytest tests/test_paradigm_api.py::TestParadigmFiles::test_file_upload -v

# Test chat completion
pytest tests/test_paradigm_api.py::TestParadigmChatCompletions::test_chat_completion_basic -v
```

## 📊 Backend API Tests

### Tested Endpoints

| Category | Endpoints | Tests |
|-----------|-----------|-------|
| Workflows | 7 endpoints | 15 tests |
| Files | 4 endpoints | 18 tests |
| Execution | 3 endpoints | 8 tests |
| PDF Export | 1 endpoint | 2 tests |

**Total: 43 backend tests**

### Backend Test Examples

```bash
# Test workflow creation
pytest tests/test_workflow_api.py::TestWorkflowCreation::test_create_simple_workflow -v

# Test workflow execution
pytest tests/test_workflow_api.py::TestWorkflowExecution::test_execute_simple_workflow -v

# Test file upload
pytest tests/test_files_api.py::TestFileUpload::test_upload_text_file -v
```

## 🔗 Integration Tests

Complete user scenario tests:

```bash
# Complete cycle: Upload → Workflow → Execution → PDF
pytest tests/test_integration.py::TestCompleteUserJourney -v

# Workflow with document search
pytest tests/test_integration.py::TestFileToWorkflowIntegration -v

# Parallel workflow execution
pytest tests/test_integration.py::TestMultipleWorkflowsParallel -v
```

**Total: 12 integration tests**

## 🔒 Security Tests

Tests for identified vulnerabilities:

```bash
# Sandbox tests (file access, OS, imports)
pytest tests/test_security.py::TestSandboxSecurity -v

# Input validation tests (XSS, SQL injection)
pytest tests/test_security.py::TestInputValidation -v

# API key exposure tests
pytest tests/test_security.py::TestAPIKeyExposure -v
```

**Total: 16 security tests**

### Tested Vulnerabilities

- ⚠️ File system access
- ⚠️ OS command injection
- ⚠️ Dangerous module imports
- ⚠️ eval/exec usage
- ⚠️ Memory exhaustion
- ⚠️ Infinite loops
- ⚠️ API key exposure
- ⚠️ Rate limiting
- ⚠️ Permissive CORS

## 🎯 Pytest Markers

Use markers to filter tests:

```bash
# Tests by category
pytest -m paradigm      # Paradigm API tests
pytest -m workflow      # Workflow API tests
pytest -m files         # Files API tests
pytest -m integration   # Integration tests
pytest -m security      # Security tests

# Exclude slow tests
pytest -m "not slow"

# Combine markers
pytest -m "paradigm and not slow"
```

## 📈 Code Coverage

```bash
# Generate coverage report
make test-coverage

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

Goal: **> 80% coverage**

## ⚡ Performance

### Performance Tests

```bash
# Concurrent requests
pytest tests/test_paradigm_api.py::TestParadigmPerformance -v

# Parallel workflows
pytest tests/test_workflow_api.py::TestWorkflowConcurrency -v
```

### Benchmark

```bash
# Run benchmarks
make benchmark
```

## 🐛 Debugging

### Verbose Tests

```bash
# Display all outputs
pytest -vv --tb=long

# Display print statements
pytest -s

# Stop at first failure
pytest -x
```

### Specific Tests

```bash
# Run a specific test
pytest tests/test_paradigm_api.py::TestParadigmDocumentSearch::test_document_search_basic -v

# Run a test class
pytest tests/test_workflow_api.py::TestWorkflowCreation -v

# Run a file
pytest tests/test_files_api.py -v
```

### Watch Mode

```bash
# Automatically rerun on changes
make test-watch
```

## 🔄 CI/CD

### GitHub Actions / GitLab CI

```yaml
# Example CI configuration
test:
  script:
    - cd tests
    - make install
    - make verify-env
    - make ci-test
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

### Required CI/CD Variables

```
LIGHTON_API_KEY
ANTHROPIC_API_KEY
```

## 📝 Writing New Tests

### Test Template

```python
import pytest
import httpx

@pytest.mark.asyncio
@pytest.mark.paradigm  # or workflow, files, etc.
async def test_my_feature(api_headers):
    """Test description"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Arrange
        payload = {"key": "value"}

        # Act
        response = await client.post(
            f"{API_BASE_URL}/endpoint",
            headers=api_headers,
            json=payload
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data
```

### Best Practices

1. **Use fixtures** for setup/cleanup
2. **Appropriate markers** (paradigm, workflow, files, security, slow)
3. **Atomic tests**: one test = one functionality
4. **Descriptive names**: `test_what_when_expected`
5. **Clear assertions** with error messages
6. **Cleanup**: delete created resources
7. **Timeouts**: always define a timeout

## 📊 Statistics

### Summary

- **Total tests**: ~97 tests
- **Coverage**: 11/11 Paradigm API endpoints
- **Execution time**: ~5-10 minutes (all tests)
- **Quick tests**: ~2 minutes

### Distribution

```
test_paradigm_api.py    : 26 tests (Paradigm API)
test_workflow_api.py    : 15 tests (Workflows)
test_files_api.py       : 18 tests (Files)
test_integration.py     : 12 tests (End-to-end)
test_security.py        : 16 tests (Security)
---
Total                   : 97 tests
```

## 🔍 Troubleshooting

### Error: LIGHTON_API_KEY not defined

```bash
# Define in .env or export
export LIGHTON_API_KEY=your_key_here
```

### Error: API not responding

```bash
# Start backend API
make start-api

# Check logs
make logs-api
```

### Tests timing out

```bash
# Increase timeouts in tests
# Or use quick tests
make test-quick
```

### Security test failures

Security tests **document vulnerabilities** identified in the analysis. Some failures are expected and indicate necessary improvements.

## 📚 References

- [Pytest Documentation](https://docs.pytest.org/)
- [HTTPX Documentation](https://www.python-httpx.org/)
- [Paradigm API Documentation](https://paradigm.lighton.ai/docs)
- [Conformity Analysis](../docs/analyse-conformite-architecture.md)

## 🤝 Contributing

To add new tests:

1. Follow the template above
2. Add appropriate markers
3. Update this README
4. Run `make test` before committing

## 📞 Support

For any questions about tests, consult:
- [Main documentation](../README.md)
- [Conformity analysis](../docs/analyse-conformite-architecture.md)
- Project GitHub Issues
