# Code signing and ALMP

## Status (November 2026)

**ALMP releases are not code-signed.** This includes v8.0.0 and v8.1.0.

ALMP applied to the [SignPath Foundation](https://signpath.org) free code-signing programme for
open-source projects. The application was **declined for now**, because the project does not yet
have enough public visibility (for example users, stars, downloads, mentions elsewhere). This is about
how well known the project is, not about the code. Reapplying later is possible, and other routes are
listed below.

## What this means for you

- Windows SmartScreen may show **"Windows protected your PC"** the first time you start ALMP.
  Click **More info**, then **Run anyway**. This warning appears for most new free programs that are
  not signed. It does not mean a virus was found.
- Only download ALMP from the project's
  [Releases page](https://github.com/alexbedca/Alexbed-Light-Media-Player/releases).
- Check the download before you run it. Every release page lists the SHA-256 checksum of the zip.
  In the folder with the zip, open PowerShell and run:

  ```powershell
  Get-FileHash .\ALMP-v8.1.0-Portable.zip -Algorithm SHA256
  ```

  or, in Command Prompt: `certutil -hashfile ALMP-v8.1.0-Portable.zip SHA256`.
  The long code must be **exactly** the same as on the release page (capital or small letters do not
  matter). If it is different, delete the file and do not run it.
- Builds made by GitHub Actions also contain `BUILD-INFO.txt`, which names the source commit and the
  workflow run that made the zip, so anyone can see how it was built.

## Why not self-sign?
A self-signed certificate is not trusted by other computers, so it changes nothing for users.
A certificate from a public authority costs money every year.

## Options that are still open

| Option | Cost | Notes |
|---|---|---|
| Reapply to SignPath Foundation later | Free for open source | Needs more public visibility first. The rest is ready: OSI licence (GPL-3.0-or-later), public repository, a released product, and a GitHub Actions build with pinned inputs. |
| SignPath (paid plan) | Paid | Same tooling, without the Foundation's visibility requirement. Check current prices on signpath.io. |
| Azure Artifact Signing (Microsoft) | Monthly fee | Identity checks take days and eligibility for individuals is limited by country; check Microsoft's current terms. |
| Microsoft Store (MSIX) | Free for individual developers | Needs MSIX packaging and identity verification by the owner. Microsoft signs the package. A good second channel. |
| Self-signed | Free | Not useful: other PCs do not trust it. |

SmartScreen reputation also grows with downloads over time, even for signed files.

## If ALMP reapplies to SignPath Foundation
- Sign `ALMP.exe` only. Every other file in the zip (Qt/PyQt6 DLLs, Python, `mpv-2.dll`, the VC++
  runtime) is third-party and is shipped unchanged and unsigned.
- Add the signing step to `.github/workflows/build.yml` only after approval, with the API token in a
  protected GitHub Environment that needs the owner's approval.
- Only then add a "Code signing policy" section to the README and release pages. Until a certificate is
  actually in use, no ALMP page should say that releases are signed.

## Until then
- Publish the SHA-256 of every zip in the release notes.
- Prefer zips built by GitHub Actions (they include `BUILD-INFO.txt`).
