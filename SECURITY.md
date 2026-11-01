# Security Policy

## Supported versions
Only the latest release receives fixes. Please update before reporting.

## Reporting a vulnerability
Please **do not** open a public issue for security problems.
Use GitHub's "Report a vulnerability" button (Security tab) or email **alexbedgh@gmail.com**.
Include the ALMP version, your Windows version and steps to reproduce.
I will reply as soon as I can and credit you in the release notes if you wish.

## Verifying downloads
Each release lists the SHA-256 checksum of the zip. In PowerShell:
`Get-FileHash .\ALMP-vX.Y.Z-Portable.zip -Algorithm SHA256`
ALMP does not connect to the internet.
