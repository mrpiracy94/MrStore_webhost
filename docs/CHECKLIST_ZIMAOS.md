# Aceitação em ZimaOS físico — MrStore_webhost v0.4

**Não preenchido:** o equipamento do proprietário não está acessível nesta sessão.
**Critério de release:** todos os testes abaixo com PASS, logs e versão de ZimaOS
identificada. Uma falha impede a declaração de compatibilidade.

- [ ] Identificar modelo, CPU/arquitetura, versão ZimaOS, kernel, Docker e suporte rootless.
- [ ] Backup externo e teste de reposição de `/DATA/AppData/MrStore_webhost/data`.
- [ ] Rootless exclusivo do `mrstore-runner`, `docker info` inclui `name=rootless`.
- [ ] Socket do Docker administrativo do ZimaOS não está montado no painel.
- [ ] Data path writable pelo utilizador rootless, sem permissões globais e sem conflito de portas.
- [ ] Painel recusa ligação intencional a daemon rootful (teste negativo, sem afetar o NAS).
- [ ] Painel arranca, login e sessão, CSRF, CRUD de projetos e ZIP com ficheiros seguros.
- [ ] HTML HTTP 200; PHP HTTP 200; React HTTP 200; Node HTTP 200, portas isoladas.
- [ ] Atualização saudável com versão anterior presente e URL estável.
- [ ] Publicação com HTTP 500/404 falha e mantém ou restaura versão anterior.
- [ ] Parar, reiniciar painel e NAS, confirmar sites e dados após reboot.
- [ ] Inspecionar logs e histórico; remover projeto e validar limpeza.
- [ ] Firewall LAN e VPN; painel não acessível publicamente por Internet.
- [ ] Confirmar `main` e GHCR (amd64/arm64), logs CI completos sem skips de testes.

Regista data, operador, evidências (logs sem passwords), PASS/FAIL e problemas
em `docs/ZIMAOS_ACCEPTANCE_RESULT.md`. Não inventar resultados.
