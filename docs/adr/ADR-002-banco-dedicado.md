# ADR-002: banco dedicado

- Status: aceito
- Data: 2026-09-08

## Contexto

O projeto precisa de dados relacionais, busca vetorial e isolamento integral de outras aplicações.

## Decisão

Usar PostgreSQL 16 com pgvector em container, rede e volume exclusivos. Objetos da aplicação vivem no schema `mentor_concursos`; IDs são UUID e timestamps são `TIMESTAMPTZ` persistidos em UTC. Migrações numeradas e imutáveis registram sua versão em `schema_migrations`.

## Consequências

O isolamento simplifica backup, restauração e controle de acesso, mas adiciona consumo de recursos. Hermes não acessa o banco. O modelo acadêmico será definido em decisões posteriores após validação do piloto.
