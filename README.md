# Mentor Concursos

Fundação versionada de um agente pessoal para a preparação de Roberto Araujo em concursos das áreas administrativa, fiscal e de tribunais. A matéria piloto é Direito Administrativo.

Este repositório contém o núcleo técnico: API interna, worker, PostgreSQL com pgvector, Redis, Apache Tika e o contrato de isolamento para uma futura instância dedicada do Hermes Agent. Nenhuma regra acadêmica foi implementada nesta fase.

## Requisitos

- Python 3.12
- Docker Engine 29.7.1 e Docker Compose 5.3.1 para validação estática e operação futura
- Ambiente Linux; datas persistidas em UTC e apresentadas em `America/Sao_Paulo`

## Desenvolvimento local

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

Prepare os segredos locais de forma idempotente, sem exibi-los:

```bash
./scripts/prepare-production-env.sh
```

O `.env` e `secrets/` reais nunca devem ser versionados. Consulte o [runbook de implantação](docs/runbooks/DEPLOY.md) antes de iniciar o núcleo.

## API

- `GET /api/health/live`: confirma que o processo responde.
- `GET /api/health/ready`: confirma consultas autenticadas no PostgreSQL e Redis.
- `GET /api/internal/auth-check`: valida o Bearer token de serviço vindo de Docker secret.

A porta `8080` é exposta apenas dentro das redes Docker, nunca publicada no host. O Hermes alcança somente a API pela rede de agente e não possui rota para banco, Redis ou Tika.

## Validação sem iniciar containers

```bash
./scripts/validate-foundation.sh
```

O script verifica arquivos, Python, testes e lint quando as ferramentas estão disponíveis, renderiza o Compose sem iniciar serviços e aplica verificações de isolamento e higiene.

## Documentação

- [Plano mestre](docs/00-PLANO-MESTRE.md)
- [Arquitetura](docs/01-ARQUITETURA.md)
- [Segurança](docs/02-SEGURANCA.md)
- [Operação](docs/03-OPERACAO.md)
- [Observabilidade mínima e egress](docs/05-OBSERVABILIDADE-E-EGRESS.md)
- [Runbook de diagnóstico](docs/runbooks/DIAGNOSTICO.md)
- [ADR-001: isolamento do Hermes](docs/adr/ADR-001-isolamento-hermes.md)
- [ADR-002: banco dedicado](docs/adr/ADR-002-banco-dedicado.md)
- [Inventário de imagens](docs/04-INVENTARIO-IMAGENS.md)
- [Runbook de implantação](docs/runbooks/DEPLOY.md)
- [Runbook de backup e restauração](docs/runbooks/BACKUP-RESTORE.md)
