# Backend Architecture

```text
backend/
  src/
    main.py    FastAPI application entrypoint
    api/       API routes
    core/      Agent orchestration, domain agents, and domain models
    data/      Document extraction and retrieval
    models/    External AI model adapters
    utils/     Project logging and other small helpers
    config.py  Typed JSON configuration loader
  config/
    config.dev.json
    config.env.json
    config.prod.json
  tests/
    unit/
    integration/
    e2e/
  requirements.txt
```

Dependencies point inward: `api` calls `core`; `core` may use `data`, `models`,
and `utils`; configuration is read through `config.py` from
`config/config.{APP_ENV}.json`, defaulting to `config/config.dev.json`.
`APP_CONFIG_FILE` can point to an exact custom config file. Secrets such as
`OPENAI_API_KEY` are injected through the process environment.
