# ADR-007 — Instância Hermes dedicada

## Status

Aceito — Fase 2A.

## Decisão

O Mentor Concursos mantém um único container `mentor-concursos-hermes`, com
volume nomeado `mentor_concursos_hermes_data`, `HERMES_HOME=/opt/data` e redes
exclusivas de agente e egress interno. O profile `mentor-concursos-hermes` é a
única forma de ativação pelo Compose.

Nenhum arquivo, volume, profile, sessão, identidade ou bind mount do Hermes de
outro projeto é reutilizado. O serviço não acessa core, banco, Redis, Tika ou
egress-uplink e não publica portas. O proxy dedicado é o único caminho externo.

## Consequências

O estado OAuth/pairing exige backup separado e rotação operacional. O dashboard
fica desativado; a entrada é somente Telegram por polling. O wrapper é parte do
controle de secrets e não deve ser substituído por um comando ad-hoc.
