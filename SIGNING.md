# Code signing plan for ALMP

ALMP is not code-signed yet, so Windows SmartScreen may warn on first run
("More info" > "Run anyway"). The free route is the **SignPath Foundation**
programme for open-source projects (https://signpath.org). This file is the
checklist for getting there. Nothing here costs money.

## Why not self-sign?
A self-signed certificate is not trusted by other computers, so it changes nothing for users.
A real certificate from a public authority costs money every year. SignPath Foundation
provides one for free to qualifying open-source projects.

## SignPath Foundation requirements (checked November 2026 - confirm on signpath.org/terms)

| Requirement | ALMP status |
|---|---|
| OSI-approved licence for all components, no commercial dual licensing | OK: GPL-3.0-or-later |
| Source repository owned by the team that signs | OK: github.com/alexbedca/Alexbed-Light-Media-Player |
| Actively maintained, already released in the form to be signed | OK (v7.2.0 released; v8.0.0 next) |
| Binaries built from source in a **verifiable** way | TODO: build on GitHub Actions (see `.github/workflows/build.yml`) |
| Manual approval of every signing request | Will be set up in SignPath |
| Product name and version set in the .exe and consistent | OK: build command sets them (`--product-name`, `--product-version`) |
| "Code signing policy" section on README and release pages | TODO: paste the text below after approval |
| Multi-factor authentication for GitHub and SignPath | TODO: check GitHub > Settings > Password and authentication |
| No hidden data collection; system changes announced | OK: ALMP is offline; startup and default-app changes are opt-in |
| Uninstall available | OK: portable app; `Remove-ALMP-Defaults.bat` undoes file associations |

## Steps

1. Turn on two-factor authentication for GitHub (done).
2. Publish v8.0.0 (unsigned) so the project "is already released".
3. Make the build reproducible on GitHub Actions (finish `.github/workflows/build.yml`: set the two libmpv variables and run it once). The workflow must download libmpv
   from a pinned, public release and record its version.
4. Apply at https://signpath.org/apply with the repository link.
5. When approved, add the SignPath step to the workflow, set yourself as author and approver.
6. Add the policy text below to README.md and to each release page.
7. Release: workflow builds, SignPath asks you to approve, signed zip is published.

## Policy text to add after approval

> **Code signing policy**
> Free code signing provided by [SignPath.io](https://signpath.io), certificate by
> [SignPath Foundation](https://signpath.org).
> Roles: Author, reviewer and approver: Alexbed ([@alexbedca](https://github.com/alexbedca)).
> Privacy: ALMP works fully offline and sends no data anywhere.

## Until then
- Publish the SHA-256 of every zip in the release notes so users can verify the download.
- Keep the Python version used for the build in the release notes.

## Other options we looked at
| Option | Cost | Verdict |
|---|---|---|
| SignPath Foundation | Free for open source | Best fit. Needs a verifiable CI build, a released product and an application; approval is by people, so it takes days. |
| Azure Artifact Signing (Microsoft) | About US$9.99/month | Individuals only in USA/Canada; identity checks take days. Does not give instant SmartScreen trust. |
| Microsoft Store (MSIX) | Free for individuals | Needs MSIX packaging and ID + selfie verification done by the owner personally. Microsoft signs the package. A good second channel later. |
| Self-signed | Free | Useless: other PCs do not trust it. |

Why it cannot be done "today": the free certificate is issued after SignPath reviews the project, and the
review wants a build made by GitHub's servers, not on a personal PC. Reputation with SmartScreen also grows
with downloads, even for signed files.
