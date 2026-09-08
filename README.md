# Mentor Concursos

Fundação versionada de um agente pessoal para a preparação de Roberto Araujo em concursos das áreas administrativa, fiscal e de tribunais. A matéria piloto é Direito Administrativo.

Este repositório contém apenas a base técnica: API interna, worker, PostgreSQL com pgvector, Redis, Apache Tika e o contrato de isolamento para uma futura instância dedicada do Hermes Agent. Nenhuma regra acadêmica foi implementada nesta fase.

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

Copie `.env.example` para `.env` somente no ambiente de implantação e substitua todos os placeholders por segredos exclusivos. O `.env` real nunca deve ser versionado.

## API

- `GET /api/health/live`: confirma que o processo responde.
- `GET /api/health/ready`: confirma conectividade TCP com PostgreSQL e Redis.

A porta `8080` é exposta apenas dentro das redes Docker, nunca publicada no host. O Hermes alcança somente a API pela rede de agente e não possui rota para banco, Redis ou Tika.

## Validação sem iniciar containers

```bash
./scripts/validate-foundation.sh
```

O script verifica arquivos, Python, testes e lint quando as ferramentas estão disponíveis, renderiza o Compose sem iniciar serviços e aplica verificações de isolamento e higiene. Consulte [docs/03-OPERACAO.md](docs/03-OPERACAO.md) antes de qualquer implantação.

## Documentação

- [Plano mestre](docs/00-PLANO-MESTRE.md)
- [Arquitetura](docs/01-ARQUITETURA.md)
- [Segurança](docs/02-SEGURANCA.md)
- [Operação](docs/03-OPERACAO.md)
- [ADR-001: isolamento do Hermes](docs/adr/ADR-001-isolamento-hermes.md)
- [ADR-002: banco dedicado](docs/adr/ADR-002-banco-dedicado.md)
