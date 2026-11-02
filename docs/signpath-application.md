# SignPath Foundation application - answers to paste

Apply at https://signpath.org/apply (the form is filled in by the project owner; check the current wording there).

| Field | Answer |
|---|---|
| Project name | Alexbed Light Media Player (ALMP) |
| Repository | https://github.com/alexbedca/Alexbed-Light-Media-Player |
| Licence | GPL-3.0-or-later (OSI-approved), no commercial dual licensing |
| Short description | A free, lightweight, fully offline Windows media player built for older and non-technical users. It plays audio and video, handles very large playlists, has a sleep timer and a high-contrast theme, and needs no installer or admin rights. |
| Download page | https://github.com/alexbedca/Alexbed-Light-Media-Player/releases |
| Build system | GitHub Actions (`.github/workflows/build.yml`), Nuitka on Python 3.13, pinned libmpv with SHA-256 check |
| Files to sign | `ALMP.exe` (and the other `.exe` files in the portable zip) |
| Maintainer / approver | Alexander Bediako (@alexbedca) |
| Privacy | ALMP works fully offline and sends no data anywhere |
| System changes | None unless the user asks: "Run at Startup" and "Set as default" are opt-in and reversible |
| Uninstall | Portable app: delete the folder; `Remove-ALMP-Defaults.bat` undoes file associations |

Before applying: (1) publish v8.0.0, (2) run the Build ALMP workflow once from the Actions tab and make sure it succeeds,
(3) confirm two-factor sign-in on GitHub (done) and on SignPath when the account is created.
