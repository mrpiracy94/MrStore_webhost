# Auditoria v0.3 — MrStore_webhost

## Resumo

- O painel é experimental e gere Docker com acesso administrativo. A v0.3 **não elimina** os privilégios efetivos associados ao socket Docker.
- A instalação local deixa painel e sites associados a `127.0.0.1`, por omissão; a variante importada no ZimaOS expõe no LAN e precisa de firewall, rede privada ou VPN.
- O deployment usa um contentor sem porta externa para o teste HTTP antes de parar o antigo. A nova release volta a ser testada após obter a porta real.
- Em falhas durante a publicação, o código tenta restaurar o contentor anterior e mantém `active_release` inalterado até à nova publicação responder corretamente.
- Um marcador de publicação pendente em `sites.json` permite retomar/recuperar estados interrompidos quando o painel reinicia. Não existem transações atómicas entre Docker e a base de dados; alguns estados de falha precisam de recuperação manual.
- A UI apresenta logs Docker e os últimos eventos de publicação, guardados em `/data/events.jsonl`.

## Aceitação antes de produção

1. CI passa testes unitários, sintáticos e integração Docker real (4 tecnologias).
2. Verifica que o pacote `ghcr.io/mrpiracy94/mrstore_webhost:0.3.0` é descarregável anonimamente, se usares a importação do ZimaOS.
3. Testa numa máquina de desenvolvimento equivalente em arquitetura e caminhos.
4. Executa testes no ZimaOS real, com snapshot/backup e com portas livres.
5. Testa indisponibilidade, restauro de versões após falha de HTTP e interrupção/reinício durante deploy.
6. Adiciona backups externos e firewall. Não exponhas o painel à Internet.

## Riscos remanescentes

- Docker socket = controlo de administrador do NAS. Nunca carregar código de projetos não confiáveis.
- Rollback best-effort; atualização não tem zero downtime, failover nem saúde contínua.
- GHCR e dependências npm precisam de Internet durante instalação/build inicial.
- PHP e Node no ambiente não são isolamento para utilizadores maliciosos; não existem quotas robustas ou limites de rede por website.
