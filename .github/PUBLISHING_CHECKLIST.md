# Publishing Checklist for Fleuve

This checklist will help you prepare and publish the Fleuve package to GitHub and PyPI.

## Pre-Publishing Checklist

### Repository Setup
- [x] All USERNAME placeholders replaced with `doomervibe`
- [x] All URLs updated to point to `github.com/doomervibe/fleuve`
- [x] Contact email set to `doomervibe111@yandex.ru`
- [x] LICENSE file present (MIT)
- [x] README.md comprehensive and complete
- [x] CHANGELOG.md up to date
- [x] CONTRIBUTING.md present
- [x] CODE_OF_CONDUCT.md present
- [x] SECURITY.md present
- [x] .gitignore properly configured
- [x] Internal todo.md file removed

### Package Configuration
- [x] pyproject.toml properly configured
- [x] Version number set (0.1.0)
- [x] Dependencies listed correctly
- [x] Package metadata complete (description, keywords, classifiers)
- [x] MANIFEST.in created for distribution
- [x] __init__.py exports all public APIs

### GitHub Features
- [x] Issue templates created (bug, feature, question)
- [x] Pull request template created
- [x] CI/CD workflows configured:
  - [x] tests.yml - Automated testing
  - [x] lint.yml - Code quality checks
  - [x] publish.yml - PyPI publishing

### Code Quality
- [x] No linter errors in fleuve/ package
- [x] Tests present and comprehensive (131 tests)
- [x] Type hints throughout codebase
- [x] Examples directory with working examples
- [x] Documentation complete

## GitHub Publishing Steps

### 1. Create GitHub Repository

```bash
# On GitHub, create a new repository named 'fleuve' under doomervibe account
# Do NOT initialize with README, .gitignore, or LICENSE (we have them)
```

### 2. Push to GitHub

```bash
# Add remote (if not already added)
git remote add origin https://github.com/doomervibe/fleuve.git

# Verify remote
git remote -v

# Push main branch
git push -u origin main

# Create and push tag for v0.1.0
git tag v0.1.0
git push origin v0.1.0
```

### 3. Configure GitHub Repository Settings

- [ ] Add repository description: "Type-safe event sourcing framework for Python"
- [ ] Add topics/tags: `event-sourcing`, `workflow`, `python`, `postgresql`, `nats`, `async`, `event-driven`
- [ ] Enable Issues
- [ ] Enable Discussions (optional)
- [ ] Configure branch protection for `main` (optional but recommended)

### 4. Set Up GitHub Secrets (for CI/CD)

If using token-based PyPI publishing:
- [ ] Add `PYPI_API_TOKEN` secret in repository settings

## PyPI Publishing Steps

### 1. Register on PyPI

- [ ] Create account at https://pypi.org
- [ ] Verify email address
- [ ] Enable 2FA (recommended)

### 2. Build Package

```bash
# Install poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Build the package
poetry build

# This creates:
# - dist/fleuve-0.1.0.tar.gz
# - dist/fleuve-0.1.0-py3-none-any.whl
```

### 3. Test on TestPyPI (Optional but Recommended)

```bash
# Configure TestPyPI
poetry config repositories.testpypi https://test.pypi.org/legacy/

# Get API token from https://test.pypi.org/manage/account/token/
poetry config pypi-token.testpypi YOUR_TESTPYPI_TOKEN

# Publish to TestPyPI
poetry publish -r testpypi

# Test installation
pip install -i https://test.pypi.org/simple/ fleuve
```

### 4. Publish to PyPI

```bash
# Get API token from https://pypi.org/manage/account/token/
poetry config pypi-token.pypi YOUR_PYPI_TOKEN

# Publish to PyPI
poetry publish

# Or build and publish in one command
poetry publish --build
```

### 5. Verify Publication

```bash
# Install from PyPI
pip install fleuve

# Verify it works
python -c "import fleuve; print(fleuve.__version__)"
```

## Post-Publishing

### GitHub

- [ ] Create release v0.1.0 on GitHub
  - [ ] Use tag v0.1.0
  - [ ] Copy changelog for v0.1.0
  - [ ] Attach built distribution files (optional)
- [ ] Update repository homepage/website
- [ ] Enable GitHub Pages for documentation (optional)

### PyPI

- [ ] Verify package appears at https://pypi.org/project/fleuve/
- [ ] Check that README renders correctly
- [ ] Verify all links work

### Announcements

- [ ] Announce on relevant Python communities (reddit.com/r/Python, etc.)
- [ ] Share on social media (optional)
- [ ] Blog post about the release (optional)

## Future Releases

For subsequent releases:

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md` with changes
3. Commit changes
4. Create and push tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
5. Create GitHub release
6. Build and publish: `poetry publish --build`

## CI/CD Automation

Once GitHub Actions are set up:

- **On Push/PR**: Tests and linting run automatically
- **On Release**: Package is automatically published to PyPI (if configured)

## Notes

- Keep `poetry.lock` in version control for reproducible builds
- Use semantic versioning (MAJOR.MINOR.PATCH)
- Always test on TestPyPI before publishing to PyPI
- Consider setting up Codecov for test coverage reporting
- Consider adding a Read the Docs site for documentation

## Troubleshooting

### Build Issues

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Rebuild
poetry build
```

### Publishing Issues

```bash
# Verify poetry configuration
poetry config --list

# Check package validity
poetry check

# Test build without publishing
poetry build --format wheel
```

### Import Issues After Install

- Ensure `__init__.py` exports all necessary classes
- Check MANIFEST.in includes all required files
- Verify dependencies are correctly listed in pyproject.toml
