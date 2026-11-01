# Contributing to ALMP

Thank you for helping! ALMP is a small, free project built for people who want a simple media player.

## Ways to help
- **Report a bug** - open an issue and say what you did, what you expected and what happened. A screenshot helps.
- **Suggest an idea** - open an issue. Please explain the problem you want solved.
- **Test releases** - especially on older or slower computers.
- **Translate or improve the documentation.**
- **Send code** - see below.

## Sending code
1. Fork the repository and create a branch.
2. Follow the "Run from source" steps in the [README](README.md).
3. Keep changes small and focused. Please open an issue first for big changes.
4. Test on Windows if you can. Run `python -m py_compile main.py` at the least.
5. Open a pull request and describe what you changed and why.

## Design rules
- Simple and readable for non-technical people comes first.
- No internet access, ads, tracking or accounts.
- The window must never freeze: slow work belongs off the main thread.

## Licence
By contributing you agree that your work is released under the project licence,
**GPL-3.0-or-later** (see [LICENSE](LICENSE)).
