# MrStore_webhost v0.4 — Docker rootless dedicado no ZimaOS

**Estado:** procedimento para administrador; **não foi executado num ZimaOS físico**.

## Preparação (não executar cegamente no NAS)
1. Backup externo de `/DATA/AppData/MrStore_webhost/data` e da v0.3.
2. Verifica versão do kernel, suporte a user namespaces, `newuidmap`/`newgidmap`,
   subuid/subgid, `systemd --user`, rootlesskit, capacidade de montar `/DATA` e persistência
   do daemon após reinícios. ZimaOS pode não disponibilizar estes requisitos.
3. Cria um **utilizador não privilegiado dedicado** `mrstore-runner` sem pertença ao grupo
   `docker`, nunca reutilizando o utilizador administrador do NAS.
4. Configura o daemon Docker rootless **para esse utilizador**, conforme guia oficial:
   https://docs.docker.com/engine/security/rootless/ . Não desligues o Docker do ZimaOS.
5. Verifica com o utilizador dedicado:
   `DOCKER_HOST=unix:///run/user/<UID>/docker.sock docker info --format '{{json .SecurityOptions}}'`
   — o resultado tem de incluir `name=rootless`.
6. Garante que o utilizador dedicado tem permissões *só* na pasta de dados
   `/DATA/AppData/MrStore_webhost/data`, incluindo releases e config. **Não uses `chmod 777`**.
   Guarda `/DATA/AppData/MrStore_webhost/data` num volume local acessível ao daemon rootless.
7. Confirma que as portas 8484 e 9101–9200 estão livres, são privadas ou filtradas
   e que o daemon rootless arranca novamente após reinício do NAS.
8. Define `WEBHOST_UID` e `WEBHOST_GID` iguais ao UID/GID do utilizador dedicado
   no Compose normal, ou a propriedade `user:` no Compose do ZimaOS.
   O painel deve ter permissões para escrever nos dados e ligar ao socket.
9. Edita `WEBHOST_ROOTLESS_SOCKET=/run/user/<UID>/docker.sock` no `.env` se utilizares
   `docker compose`; ou altera a montagem correspondente de `zimaos-compose.yml`.
   O socket é montado no painel como `/run/mrstore/docker.sock`.
10. Liga o painel via Compose, vê os logs e confirma mensagem de arranque. Se o daemon
   for rootful, o painel **recusa arrancar**. A ligação está fixada no código.
11. Testa publicação HTML, PHP, Node e React, 404, rollback, logs e recuperação,
    usando `docs/CHECKLIST_ZIMAOS.md` antes de qualquer exposição à rede.

## Nota sobre migração

O daemon rootless dedicado não vê os contentores criados pelo Docker rootful
anterior. Faz backup dos dados e republica a partir do painel novo. Não apagues
contentores antigos sem identificar qual serviço usa cada um.
O Docker rootless continua a dar controlo ao painel sobre os contentores e ficheiros
**acessíveis ao utilizador rootless**. Não garante isolamento de multiutilizador.
Os limites de memória/PIDs podem ser ignorados em servidores sem cgroup v2/systemd.

Referências: https://docs.docker.com/engine/security/rootless/ e
https://docs.docker.com/engine/security/rootless/tips/
