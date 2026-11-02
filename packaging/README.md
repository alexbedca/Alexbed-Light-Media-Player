# Packaging drafts (not submitted)

These files are **drafts**. Nothing here has been submitted to winget or Scoop, and nothing in ALMP
downloads or updates itself: these package managers only help a person (or a helper setting up a PC)
install the same portable zip that is on the Releases page.

| File | For | Status |
|---|---|---|
| `winget/Alexbed.ALMP.yaml` | [winget](https://github.com/microsoft/winget-pkgs) (`winget install Alexbed.ALMP`) | Draft, singleton format, hash is a placeholder |
| `scoop/almp.json` | a Scoop bucket (for example `extras`) | Draft, hash is a placeholder |

## Before submitting
1. Publish the release zip built by GitHub Actions (not a local build; Nuitka builds are not byte-identical).
2. Put that zip's SHA-256 (from the Actions run summary) in both files, and check the URL and folder name.
3. winget: `winget validate --manifest packaging\winget\Alexbed.ALMP.yaml`, then
   `winget install --manifest packaging\winget\Alexbed.ALMP.yaml` on a test PC. winget-pkgs expects the
   multi-file format: `wingetcreate new <zip url>` produces it from the same information.
   Unsigned portable zips are accepted; Microsoft scans them during validation.
4. Scoop: test with `scoop install .\packaging\scoop\almp.json`, then open a pull request to the bucket.
5. Update both files for every release (version, URL, hash).
