# Security Policy

## Supported Versions

Security fixes are currently focused on the latest code in the `main` branch.

## Reporting a Vulnerability

Please do not publish API keys, private chat logs, or exploit details in a public issue.

If you find a security issue, open a GitHub issue with a minimal description and mark it as security-sensitive if GitHub offers that option. Include:

- Operating system and Elyra version or commit.
- Provider in use, without sharing API keys.
- Steps to reproduce using fake secrets and non-private data.

## Privacy Notes

Elyra stores chat history and settings locally in the user's application data directory. API keys are saved locally and are not intentionally logged.

Voice recognition uses the SpeechRecognition Google backend by default, and speech synthesis uses edge-tts. Those voice features may send audio or text to external services. Users who need fully local operation should disable voice features or replace them with local engines.
