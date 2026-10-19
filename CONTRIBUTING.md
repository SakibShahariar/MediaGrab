# Contributing to MediaGrab

Thanks for your interest in MediaGrab. The project is at an early stage, so focused proposals and small, testable contributions are especially helpful.

## Before starting

- Check existing issues and discussions before opening a duplicate.
- For substantial changes, open an issue first to agree on scope and expected behavior.
- Keep browser integration, media inspection, transfer logic, and UI concerns separated.

## Pull requests

- Explain the user-visible problem or improvement.
- Include steps to reproduce or test the change.
- Add tests for parsing, transfer behavior, and message validation when applicable.
- Document unsupported cases and meaningful limitations.
- Do not include cookies, tokens, private URLs, browser profiles, or captured personal data in logs or test fixtures.

## Research and third-party code

MediaGrab may study observable behavior of existing download tools to understand user workflows. Do not submit proprietary source code, extracted proprietary assets, or third-party extension packages. Implement features independently using documented APIs and appropriately licensed resources.

## Reporting bugs

Include the MediaGrab version or commit, Linux distribution, desktop/session details when relevant, browser version for integration issues, expected behavior, actual behavior, and reproducible steps. Redact credentials and private media URLs.
