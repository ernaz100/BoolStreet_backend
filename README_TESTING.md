# BoolStreet Backend Testing Suite

This document describes the comprehensive testing suite for the BoolStreet backend application.

## 📋 Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Coverage Reports](#coverage-reports)
- [Writing New Tests](#writing-new-tests)
- [Continuous Integration](#continuous-integration)

## 🔍 Overview

The testing suite provides comprehensive coverage for all backend functionalities including:

- **Authentication**: Google OAuth integration and JWT token handling
- **Scripts**: Trading script upload, execution, and management
- **Dashboard**: Statistics and predictions retrieval
- **Market Data**: Market overview and top movers data
- **Leaderboard**: Trader rankings and performance tracking
- **Database Models**: Data integrity and relationships

## 🏗️ Test Structure

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Test fixtures and configuration
│   ├── test_auth.py          # Authentication tests
│   ├── test_scripts.py       # Script management tests
│   ├── test_dashboard.py     # Dashboard functionality tests
│   ├── test_market_data.py   # Market data API tests
│   ├── test_leaderboard.py   # Leaderboard tests
│   └── test_models.py        # Database model tests
├── pytest.ini               # Pytest configuration
├── run_tests.py              # Test runner script
└── README_TESTING.md         # This document
```

## 🛠️ Installation

### Prerequisites

1. **Python Environment**: Ensure you have Python 3.8+ and virtual environment activated
2. **Dependencies**: Install test dependencies

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install test dependencies
pip install -r requirements.txt
```

### Test Dependencies

The following testing packages are included in `requirements.txt`:

- `pytest==8.0.2` - Testing framework
- `pytest-flask==1.3.0` - Flask testing utilities
- `pytest-mock==3.12.0` - Mocking utilities
- `pytest-cov==4.0.0` - Coverage reporting
- `factory-boy==3.3.0` - Test data factories

## 🚀 Running Tests

### Using the Test Runner Script (Recommended)

The `run_tests.py` script provides a convenient interface for running tests:

```bash
# Run all tests
python run_tests.py

# Run specific test categories
python run_tests.py --auth        # Authentication tests only
python run_tests.py --api         # API tests only
python run_tests.py --database    # Database tests only
python run_tests.py --unit        # Unit tests only
python run_tests.py --integration # Integration tests only

# Run specific test file
python run_tests.py --file auth   # Run test_auth.py
python run_tests.py --file models # Run test_models.py

# Coverage and reporting options
python run_tests.py --coverage    # Generate detailed coverage report
python run_tests.py --no-cov      # Disable coverage reporting
python run_tests.py --verbose     # Verbose output
python run_tests.py --quiet       # Quiet output

# Performance options
python run_tests.py --fast        # Skip slow tests
python run_tests.py --parallel    # Run tests in parallel (requires pytest-xdist)
```

### Using Pytest Directly

For more control, you can use pytest commands directly:

```bash
# Basic test running
pytest                            # Run all tests
pytest tests/                     # Run all tests in tests directory
pytest tests/test_auth.py         # Run specific test file
pytest tests/test_auth.py::TestAuthAPI::test_google_auth_success  # Run specific test

# Test selection by markers
pytest -m "auth"                  # Run tests marked with @pytest.mark.auth
pytest -m "api"                   # Run API tests
pytest -m "database"              # Run database tests
pytest -m "not slow"              # Skip slow tests
pytest -m "auth and not slow"     # Authentication tests that aren't slow

# Coverage reporting
pytest --cov=.                    # Basic coverage
pytest --cov=. --cov-report=html  # HTML coverage report
pytest --cov=. --cov-report=term-missing  # Terminal report with missing lines
pytest --cov=apis --cov=db        # Coverage for specific modules only

# Output and verbosity
pytest -v                         # Verbose output
pytest -q                         # Quiet output
pytest -s                         # Don't capture output (show print statements)
pytest --tb=short                 # Short traceback format
pytest --tb=long                  # Long traceback format

# Test execution control
pytest -x                         # Stop on first failure
pytest --maxfail=3                # Stop after 3 failures
pytest --lf                       # Run last failed tests only
pytest --ff                       # Run failures first, then the rest

# Parallel execution (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto                    # Auto-detect CPU cores
pytest -n 4                       # Use 4 workers

# Performance and profiling
pytest --durations=10             # Show 10 slowest tests
pytest --setup-show               # Show fixture setup/teardown
```

### Quick Command Reference

| Command | Description |
|---------|-------------|
| `python run_tests.py` | Run all tests with coverage |
| `python run_tests.py --auth` | Run authentication tests only |
| `python run_tests.py --file auth` | Run test_auth.py |
| `pytest tests/test_auth.py -v` | Run auth tests with verbose output |
| `pytest -m "not slow"` | Skip slow tests |
| `pytest --lf` | Re-run last failed tests |
| `pytest --cov=. --cov-report=html` | Generate HTML coverage report |

## 🏷️ Test Categories

Tests are organized using pytest markers:

### Markers Available

- `@pytest.mark.unit` - Unit tests (isolated functionality)
- `@pytest.mark.integration` - Integration tests (multiple components)
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.auth` - Authentication-related tests
- `@pytest.mark.database` - Database model and interaction tests
- `@pytest.mark.slow` - Tests that take longer to execute

### Test Coverage by Module

#### 🔐 Authentication (`test_auth.py`)
- Google OAuth token verification
- JWT token creation and validation
- User creation and updates
- Protected route access
- Error handling scenarios

#### 📜 Scripts (`test_scripts.py`)
- Script upload and validation
- Script listing and management
- Script activation/deactivation
- File upload error handling
- Script execution integration

#### 📊 Dashboard (`test_dashboard.py`)
- Dashboard statistics calculation
- Recent predictions retrieval
- User-specific data filtering
- Empty state handling

#### 📈 Market Data (`test_market_data.py`)
- Market overview data formatting
- Top movers data retrieval
- Data fallback scenarios
- Error handling for missing data

#### 🏆 Leaderboard (`test_leaderboard.py`)
- Leaderboard data retrieval
- Trader ranking logic
- Current user identification
- Initial data creation

#### 🗄️ Models (`test_models.py`)
- Model creation and validation
- Relationship testing
- Default value handling
- String representation methods

## 📊 Coverage Reports

### Generating Coverage Reports

Coverage reports are automatically generated when running tests:

```bash
# Generate HTML coverage report
python run_tests.py --coverage

# View coverage in terminal
pytest --cov=. --cov-report=term-missing

# Generate XML coverage for CI
pytest --cov=. --cov-report=xml
```

### Coverage Files

- **HTML Report**: `htmlcov/index.html` - Interactive coverage report
- **Terminal Report**: Shows coverage percentages and missing lines
- **XML Report**: `coverage.xml` - For CI/CD integration

### Coverage Targets

- **Minimum Coverage**: 80% overall
- **Critical Modules**: 90%+ coverage required for:
  - Authentication (`apis/auth.py`)
  - Database models (`db/models.py`)
  - Core APIs (`apis/*.py`)

## ✍️ Writing New Tests

### Test File Structure

```python
"""
Test suite for [module] functionality.
Brief description of what this module tests.
"""

import pytest
import json
from unittest.mock import patch


class Test[ModuleName]API:
    """Test class for [module] API endpoints."""

    def test_[function_name]_success(self, client, auth_headers):
        """
        Test successful [operation].
        Should [expected behavior].
        """
        # Arrange
        # ... setup test data
        
        # Act
        response = client.get('/endpoint', headers=auth_headers)
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'expected_field' in data

    def test_[function_name]_error_case(self, client):
        """
        Test [operation] error case.
        Should return appropriate error.
        """
        # Test implementation
```

### Best Practices

1. **Test Naming**: Use descriptive names that explain what is being tested
2. **AAA Pattern**: Arrange, Act, Assert
3. **One Assertion Per Test**: Focus on testing one specific behavior
4. **Mock External Dependencies**: Use mocks for databases, APIs, file systems
5. **Test Edge Cases**: Include error conditions, empty data, invalid inputs
6. **Use Fixtures**: Leverage pytest fixtures for common setup

### Common Fixtures Available

```python
# From conftest.py
def test_example(client, auth_headers, mock_db_session, sample_user):
    """Example test using common fixtures."""
    # client - Flask test client
    # auth_headers - Pre-configured JWT headers
    # mock_db_session - Mocked database session
    # sample_user - Sample user data
```

### Adding New Fixtures

Add new fixtures to `conftest.py`:

```python
@pytest.fixture
def sample_custom_data():
    """Create sample data for testing."""
    return {
        'field1': 'value1',
        'field2': 'value2'
    }
```

## 🔄 Continuous Integration

### GitHub Actions Integration

Create `.github/workflows/test.yml`:

```yaml
name: Backend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: |
        cd backend
        pip install -r requirements.txt
    - name: Run tests
      run: |
        cd backend
        python run_tests.py --coverage
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

### Pre-commit Hooks

Add to `.pre-commit-config.yaml`:

```yaml
repos:
- repo: local
  hooks:
  - id: pytest
    name: pytest
    entry: bash -c 'cd backend && python run_tests.py --fast'
    language: system
    pass_filenames: false
```

## 🔧 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the backend directory
2. **Database Errors**: Tests use in-memory SQLite, no external DB needed
3. **Missing Dependencies**: Run `pip install -r requirements.txt`
4. **Environment Variables**: Tests use mocked environment variables

### Debug Mode

```bash
# Run specific test with debug output
pytest tests/test_auth.py::TestAuthAPI::test_google_auth_success -v -s

# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest --tb=long
```

### Performance

```bash
# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto

# Profile slow tests
pytest --durations=10
```

## 📝 Contributing

When adding new functionality:

1. **Write tests first** (TDD approach recommended)
2. **Ensure >80% coverage** for new code
3. **Update this documentation** if adding new test categories
4. **Run full test suite** before submitting PRs

### Test Checklist

- [ ] Tests cover happy path scenarios
- [ ] Tests cover error conditions
- [ ] Tests cover edge cases
- [ ] All tests pass locally
- [ ] Coverage requirements met
- [ ] Documentation updated

---

For questions or issues with the testing suite, please check the existing tests for examples or reach out to the development team. 