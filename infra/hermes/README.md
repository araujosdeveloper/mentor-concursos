# Hermes dedicado do Mentor Concursos

## Isolamento

O serviço `mentor-concursos-hermes` usa exclusivamente a imagem
`ghcr.io/hostinger/hvps-hermes-agent@sha256:7af25fad2af3673f5be39824e38772a9895cb70af83c157917b4cd5e3983e9f9`
(Hermes Agent v0.20.4), o volume `mentor_concursos_hermes_data` e as redes
`mentor-concursos-agent` e `mentor-concursos-egress-internal`. Ele nunca entra
na rede core nem na `egress-uplink`; a internet só é alcançada pelo proxy
`mentor-concursos-egress-proxy`. Não há `ports`, `network_mode: host`, socket
Docker, bind mount do Hermes antigo ou compartilhamento de estado.

O estado persistente fica em `HERMES_HOME=/opt/data`. O wrapper
`entrypoint.sh` lê os Docker secrets em modo somente leitura, mantém o token do
Telegram apenas em memória e copia o token de serviço, durante o bootstrap,
somente para um arquivo 0400 em `/run` (tmpfs). Templates de personalidade são
semeados apenas quando ausentes; OAuth, pairing, sessões e memória nunca são
sobrescritos.

## Identidade e autorização

`SOUL.md`, `AGENTS.md`, `USER.md` e `MEMORY.md` são próprios do Mentor
Concursos. Telegram usa polling, DM pairing e `group_policy: disabled`. A única
autorização aprovada é o usuário Roberto Araujo (ID registrado no estado local;
tokens nunca entram em Git/relatórios). Para revogação imediata, use
`hermes pairing revoke telegram <id>` no volume dedicado e reinicie somente o
Hermes. Para rotação do bot, substitua o arquivo host com modo 600 e recrie
somente o serviço; não grave o valor no Compose.

## Modelo e saúde

O provider é `openai-codex`, autenticado por um fluxo OAuth novo no volume
dedicado. O modelo selecionado a partir da lista real oferecida pela versão
instalada é `gpt-5.6-sol`. O healthcheck valida o PID JSON do gateway e a
existência de `gateway_state.json`; dashboard não é superfície desta fase.

Consulte [HERMES-TELEGRAM.md](../../docs/runbooks/HERMES-TELEGRAM.md) para
pairing, backup, rollback e diagnóstico.
