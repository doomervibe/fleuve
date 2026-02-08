# Security Policy

## Supported Versions

We currently support the following versions of Fleuve with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability, please follow these steps:

### 1. **Do NOT** open a public issue

Security vulnerabilities should be reported privately to protect users until a fix is available.

### 2. Email the security team

Send an email to: **doomervibe111@yandex.ru**

Please include:
- A clear description of the vulnerability
- Steps to reproduce the issue
- Potential impact and severity assessment
- Any suggested fixes or mitigations (if available)

### 3. What to expect

- **Acknowledgment**: You will receive an acknowledgment within 48 hours
- **Initial Assessment**: We will assess the vulnerability within 7 days
- **Updates**: We will provide regular updates on the status of the fix
- **Disclosure**: After a fix is released, we will disclose the vulnerability (with credit if desired)

### 4. Response timeline

- **Critical vulnerabilities**: Response within 24 hours, fix within 7 days
- **High severity**: Response within 48 hours, fix within 14 days
- **Medium/Low severity**: Response within 7 days, fix in next release

## Security Best Practices

When using Fleuve in production:

1. **Encryption**: Use `STORAGE_KEY` environment variable for event encryption
2. **Database Security**: Use strong passwords and secure PostgreSQL connections
3. **Network Security**: Ensure NATS server is not publicly accessible
4. **Dependencies**: Keep dependencies up to date
5. **Access Control**: Implement proper access controls for your workflows
6. **Secrets Management**: Never commit secrets or API keys to version control

## Known Security Considerations

### Event Data Encryption

Fleuve supports encrypting event data at rest using the `EncryptedPydanticType`. Ensure you:
- Use a strong, randomly generated encryption key (32+ characters)
- Store the key securely (environment variables, secret management systems)
- Rotate keys periodically
- Never commit encryption keys to version control

### Database Access

- Use connection pooling appropriately
- Implement database-level access controls
- Use SSL/TLS for database connections in production
- Regularly update PostgreSQL to latest stable version

### NATS Security

- Configure NATS authentication and authorization
- Use TLS for NATS connections in production
- Restrict network access to NATS server
- Monitor NATS for unusual activity

## Security Updates

Security updates will be:
- Released as patch versions (e.g., 0.1.1, 0.1.2)
- Documented in CHANGELOG.md
- Announced via GitHub releases
- Backported to supported versions when possible

## Reporting Non-Security Bugs

For non-security bugs, please use the [GitHub Issues](https://github.com/doomervibe/fleuve/issues) page.

## Security Audit

If you've performed a security audit of Fleuve and found issues, we'd love to hear from you! Please follow the vulnerability reporting process above.

## Credits

We appreciate responsible disclosure and will credit security researchers who report vulnerabilities (if desired).
