# SignPath Foundation application - record

**Outcome (November 2026): declined for now.** The reason given was that the project lacks public
visibility. ALMP releases stay unsigned (see [SIGNING.md](../SIGNING.md)). This page is kept so a later
reapplication can start from corrected answers.

Apply at https://signpath.org/apply (the form is filled in by the project owner; check the current wording there).

| Field | Answer |
|---|---|
| Project name | Alexbed Light Media Player (ALMP) |
| Repository | https://github.com/alexbedca/Alexbed-Light-Media-Player |
| Licence | GPL-3.0-or-later (OSI-approved), no commercial dual licensing |
| Short description | A free, lightweight, fully offline Windows media player built for older and non-technical users. It plays audio and video, handles very large playlists, has a sleep timer and a high-contrast theme, and needs no installer or admin rights. |
| Download page | https://github.com/alexbedca/Alexbed-Light-Media-Player/releases |
| Build system | GitHub Actions (`.github/workflows/build.yml`): Nuitka on Python 3.13, version read from `main.py`, libmpv URL and SHA-256 written in the workflow, actions pinned to commit SHAs |
| Files to sign | `ALMP.exe` only. All other files in the zip are third-party and are shipped unchanged and unsigned. |
| Maintainer / approver | Alexander Bediako (@alexbedca) |
| Privacy | This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. (ALMP works fully offline; its error log stays on the PC.) |
| System changes | None unless the user asks: "Run at Startup" and "Set as default" are opt-in and reversible |
| Uninstall | Portable app: run `Remove-ALMP-Defaults.bat` (removes file associations, the startup shortcut and, if the user agrees, ALMP's settings and log), then delete the folder |

Before reapplying: (1) grow public visibility (users, stars, downloads, mentions), (2) run the Build ALMP
workflow from the Actions tab and publish a release built by it, (3) keep two-factor sign-in on GitHub,
and set it up on SignPath when the account is created.
