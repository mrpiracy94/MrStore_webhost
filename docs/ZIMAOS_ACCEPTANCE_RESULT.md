# Aceitação física ZimaOS — v0.4 (candidata)

**Estado: POR VALIDAR NO NAS.** O GitHub Actions usa runners Ubuntu com Docker rootless e **não** prova compatibilidade no ZimaOS.

## Evidência automática já obtida

- GitHub Actions em Docker rootless (31 testes e quatro websites HTML/PHP/Node/React): [execução #37857937250](https://github.com/mrpiracy94/MrStore_webhost/actions/runs/37857937250) — sucesso.
- Smoke tests adicionais de atualização, falha HTTP e reinício do painel: **dependem de nova execução CI**.
- Imagem 0.4.0-rc (amd64, arm64): **confirmar execução do job image e acessibilidade pública antes de instalar**.
- Versão 0.4.0 final: **não publicada em main**.

## Registo obrigatório no ZimaOS real

Preencher apenas com evidência recolhida no equipamento, nunca por pressuposição.

| Teste | Resultado | Evidência sem segredos |
|---|---|---|
| Modelo NAS / CPU / versão ZimaOS / kernel | PENDENTE | |
| Backup externo e restauro de teste | PENDENTE | |
| Docker rootless dedicado persiste depois do reinício | PENDENTE | |
| Utilizador dedicado fora do grupo docker | PENDENTE | |
| `sh scripts/zimaos_preflight.sh` | PENDENTE | |
| Socket rootful não montado; rootless reconhecido | PENDENTE | |
| Imagem RC acessível ao ZimaOS | PENDENTE | |
| Login, sessão e upload ZIP | PENDENTE | |
| HTML / PHP / React / Node: HTTP 200 | PENDENTE | |
| Atualização, rollback HTTP 500, logs | PENDENTE | |
| Reinício do painel e do NAS, persistência | PENDENTE | |
| Firewalls, acesso só pela LAN/VPN | PENDENTE | |

**Gate:** só promover para `main` quando os itens obrigatórios acima forem aprovados num ZimaOS real e a imagem RC passar no GitHub Actions. Evitar publicar dados pessoais, passwords, `.env` ou tokens nos logs.
