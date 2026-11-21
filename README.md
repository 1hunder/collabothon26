# collabothon26

## Run with Docker

From the repository root, run:

```sh
docker compose -f docker-compose.yml -f compose.yaml --profile api up --build -d
docker compose -f docker-compose.yml -f compose.yaml --profile api exec api python -m financequest db upgrade
docker compose -f docker-compose.yml -f compose.yaml --profile api exec api python -m financequest refpack approve financequest/fixtures/reference/fq-av-001
```

Open [Finance Quest](http://localhost:4173). The local stack defaults to scripted narration and runs without API keys.

Stop the stack with `docker compose -f docker-compose.yml -f compose.yaml --profile api down`.
