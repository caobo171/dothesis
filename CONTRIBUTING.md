# Contributing to DoThesis

Thanks for your interest in contributing to DoThesis!

## Quick Start

```bash
git clone https://github.com/federicodeponte/dothesis.git
cd dothesis
cp .env.example .env          # fill in keys (Gemini at minimum)
./dev.sh                      # API :7100, web :3006
```

For the standalone engine only:

```bash
pip install -e ./engine[dev]
cd engine && pytest tests/ -v
```

## Development Setup

1. **Python 3.13** (API venv) and **Node 18+** (web). Engine works on 3.10+.
2. **PostgreSQL** (local, port 5499 per the default `DATABASE_URL`).
3. A **Gemini API key** — set `GEMINI_API_KEY`/`GOOGLE_API_KEY` in `.env`. `ANTHROPIC_API_KEY` switches the agent to Claude.
4. Read [`AGENTS.md`](AGENTS.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before touching the agent, skills, state, or API.

## Code Structure

```
dothesis/
├── web/            # Next.js chat workspace
├── api/            # FastAPI gateway (POST-only)
├── agent/          # deep-agent chat runtime + tools
├── skills/         # M1–M5 + routing + bootstrap skills (chat behavior)
├── orchestrator/   # auto-approve LangGraph graph + agents + M5 export
├── engine/         # research + writing engine (also a standalone CLI)
└── docs/           # documentation
```

## Conventions (please follow)

- **POST-only endpoints.** New API routes are `@router.post`; the auth token rides in the JSON body. Only `/api/v1/health` is GET.
- **Comment the reasoning** behind non-obvious changes (a short note on *why*, not *what*).
- **Behavior lives in skills/prompts.** Change a module's behavior in its `skills/*/SKILL.md` (chat) or `orchestrator/prompts` + agent class (auto) first, then the code.
- Don't run `next build` while `dev.sh`'s `next dev` is running — it serves stale UI.

## Making Changes

1. Fork the repo
2. Create a branch (`git checkout -b feature/your-feature`)
3. Make changes
4. Run tests (`pytest tests/ -v`)
5. Commit (`git commit -m "feat: your feature"`)
6. Push and open a PR

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance

## What to Contribute

- Bug fixes
- Documentation improvements
- New citation sources
- New export formats
- Performance improvements
- Test coverage

## Questions?

Open an issue or reach out to [@federicodeponte](https://github.com/federicodeponte).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
