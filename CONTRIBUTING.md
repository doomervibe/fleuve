# Contributing to Fleuve

Thank you for your interest in contributing to Fleuve! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.13+
- PostgreSQL 12+ (for running tests)
- NATS Server 2.9+ (for running tests)
- Poetry (for dependency management)

### Setting Up Development Environment

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/doomervibe/fleuve.git
   cd fleuve
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

3. **Set up test infrastructure**:
   ```bash
   # Start PostgreSQL (using Docker)
   docker run -d --name fleuve-postgres \
     -e POSTGRES_PASSWORD=postgres \
     -p 5432:5432 \
     postgres:16

   # Start NATS (using Docker)
   docker run -d --name fleuve-nats \
     -p 4222:4222 \
     nats:latest -js
   ```

4. **Set environment variables**:
   ```bash
   export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/fleuve"
   export TEST_NATS_URL="nats://localhost:4222"
   ```

5. **Run tests**:
   ```bash
   poetry run pytest
   ```

## Development Workflow

### Code Style

- **Formatting**: We use [Black](https://black.readthedocs.io/) for code formatting
  ```bash
   poetry run black fleuve/
   ```

- **Type Hints**: All code must include type hints. We use mypy for type checking:
  ```bash
   poetry run mypy fleuve/
   ```

- **Import Organization**: Imports should be organized as:
  1. Standard library imports
  2. Third-party imports
  3. Local application imports

### Testing

- **Write tests** for all new features and bug fixes
- **Run tests** before submitting:
  ```bash
   poetry run pytest fleuve/tests/ -v
   ```

- **Test coverage**: Aim for high test coverage. Check coverage with:
  ```bash
   poetry run pytest --cov=fleuve --cov-report=html
   ```

### Documentation

- **Docstrings**: All public functions, classes, and methods should have docstrings
- **Type hints**: Use type hints in function signatures
- **README**: Update README.md if adding new features or changing behavior
- **Examples**: Add examples to the examples/ directory for new features

## Submitting Changes

### Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

2. **Make your changes**:
   - Write code following the style guidelines
   - Add tests for your changes
   - Update documentation as needed
   - Ensure all tests pass

3. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add feature: description of your changes"
   ```
   
   Use clear, descriptive commit messages:
   - Start with a verb (Add, Fix, Update, Remove)
   - Keep the first line under 72 characters
   - Add more details in the body if needed

4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request**:
   - Fill out the PR template
   - Reference any related issues
   - Request review from maintainers

### Pull Request Checklist

- [ ] Code follows the project's style guidelines
- [ ] All tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated (README, docstrings, etc.)
- [ ] CHANGELOG.md updated (if applicable)
- [ ] No linter errors
- [ ] Self-reviewed the code

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- **Description**: Clear description of the bug
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**: Python version, OS, dependencies versions
- **Error Messages**: Full error messages and stack traces
- **Minimal Example**: If possible, provide a minimal code example

### Feature Requests

When requesting features, please include:

- **Use Case**: Why this feature would be useful
- **Proposed Solution**: How you envision it working
- **Alternatives**: Alternative solutions you've considered
- **Additional Context**: Any other relevant information

## Code Review Process

- All PRs require at least one review from a maintainer
- Address review comments promptly
- Be open to feedback and suggestions
- Keep discussions focused and constructive

## Questions?

If you have questions about contributing:

- Open an issue with the `question` label
- Check existing issues and discussions
- Review the README.md for documentation

## License

By contributing to Fleuve, you agree that your contributions will be licensed under the MIT License.
