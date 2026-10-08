# MrStore_webhost v0.4 — Alojamento web para ZimaOS

Painel em português para publicar **HTML, PHP, React/Vite e Node.js** em contentores Docker independentes. Código disponível neste **repositório independente** (`mrpiracy94/MrStore_webhost`), sem dependências da MrStore.

> **Estado: versão experimental para uso numa LAN de confiança.** A execução em ZimaOS físico ainda não está validada. A v0.4 exige um daemon Docker rootless separado. **Não exponhas o painel diretamente à Internet.**

## Alteração importante de segurança — Docker rootless obrigatório

A v0.4 recusa a ligação ao Docker administrativo, incluindo o socket `/var/run/docker.sock`. Exige um **daemon Docker rootless dedicado**, com socket montado em `/run/mrstore/docker.sock` dentro do painel e validação `SecurityOptions: name=rootless` no arranque. O painel mantém o controlo dos contentores e ficheiros permitidos ao utilizador rootless, mas deixa de ter acesso administrativo ao daemon principal do ZimaOS.

Lê [docs/ROOTLESS_SETUP.md](docs/ROOTLESS_SETUP.md) antes da atualização. O novo daemon não vê os contentores antigos: faz backup dos dados e republica os websites. A compatibilidade física com ZimaOS continua por comprovar.

## Release candidate para instalação de teste no ZimaOS

A branch `stabilization/rootless-ci-zimaos` constrói a imagem **`ghcr.io/mrpiracy94/mrstore_webhost:0.4.0-rc`** depois dos testes unitários e de integração Docker rootless terem sucesso. O manifesto `zimaos-compose.yml` desta branch aponta para essa candidata. **Só instala depois de verificar o job `image` e de confirmar que o pacote GHCR está publicamente acessível**. A versão `0.4.0` final só será publicada ao integrar na `main` após aceitação física.

A integração automatizada testa as quatro tecnologias, uma atualização válida, a rejeição de uma atualização HTTP 500 e a sobrevivência dos websites após reinício do painel. Estes testes **não substituem** o teste no NAS após reinício do equipamento.

## Novidades da v0.4

- **HTTP readiness:** antes de parar o website antigo, inicia a nova release num contentor sem porta publicada e verifica HTTP internamente. Após a troca de portas, repete a verificação HTTP. Códigos 2xx/3xx são considerados prontos; uma rota `/` que devolva 404, 401 ou 500 é considerada falha. Para uma API sem rota `/`, cria uma rota inicial saudável.
- **Recuperação:** mantém o contentor anterior até a nova versão responder, escreve um marcador persistente de publicação em `sites.json` e recupera publicações interrompidas no arranque do painel. Não é recuperação transacional para todo e qualquer cenário de falha, nem zero downtime.
- **Logs:** histórico de publicação por website, mensagens de erro e logs do contentor no painel; jornal limitado a 2 MB antes de uma rotação simplificada.
- **Docker CLI sem `apk add` no arranque:** o `Dockerfile` copia um Docker CLI durante a construção. A instalação via importação do ZimaOS passa a usar uma imagem GHCR preconstruída **apenas após** a workflow `CI and container release` ter passado e a imagem estar publicamente acessível no GHCR.
- **Segurança de rede:** `docker-compose.yml` publica a porta do painel e as portas dos sites apenas em `127.0.0.1` por omissão. Abre para a LAN de forma intencional quando precisares. A configuração `zimaos-compose.yml` publica no LAN para acesso direto e deve ficar atrás de firewall/VPN.
- **CI:** testes Python e JavaScript, integração com Docker real para HTML, PHP, Node e React, e publicação de imagem AMD64/ARM64 no GHCR **depois dos testes passarem**. A existência do workflow não prova que já tenha executado com sucesso.

## Instalar via Docker Compose (recomendado para primeiro teste)

1. Configura primeiro um Docker rootless dedicado e confirma que o utilizador tem acesso ao diretório de dados. Consulta `docs/ROOTLESS_SETUP.md`. Confirma que a porta 8484 e 9101–9200 estão livres.
2. Clona o repositório. Copia `.env.example` para `.env`, define uma `WEBHOST_ADMIN_PASSWORD` de pelo menos 12 caracteres, o caminho `WEBHOST_DATA_DIR`, `WEBHOST_ROOTLESS_SOCKET` e o UID/GID do utilizador rootless. Para a LAN, define **explicitamente** os IPs de bind.
3. Executa `docker compose up -d --build` e consulta os logs com `docker compose logs -f`.
4. Abre `http://127.0.0.1:8484` no próprio host (ou `http://IP_LAN:8484` se ativares acesso LAN). Usa uma VPN ou túnel SSH para acesso remoto.

Os websites criados terão portas 9101–9200, também associadas ao `WEBHOST_SITE_BIND_IP` definido. Numa instalação com bind a `127.0.0.1`, outras máquinas não conseguem alcançar os sites diretamente. A imagem local constrói-se durante a instalação, mas **não precisa de descarregar Docker CLI a cada arranque**.

## Instalar pelo importador do ZimaOS

1. Abre as execuções do GitHub Actions e confirma que `CI and container release` terminou sem erros e publicou `ghcr.io/mrpiracy94/mrstore_webhost:0.4.0` para AMD64/ARM64.
2. Confirma que o pacote GHCR está **público** (a publicação num repositório público não garante visibilidade pública automática do pacote). Se a imagem não puder ser descarregada anonimamente, utiliza a instalação por terminal/Compose.
3. Configura o Docker rootless no ZimaOS (se suportado) e executa `sh scripts/zimaos_preflight.sh` como utilizador dedicado. Edita `zimaos-compose.yml`: substitui `ADMIN_PASSWORD`, o UID/GID, o caminho do socket rootless, as portas e o volume de dados. Faz backup antes de atualizar.
4. Importa o ficheiro `zimaos-compose.yml` em **Aplicação personalizada → Importar Docker Compose**.
5. Abre o painel em `http://IP_DO_ZIMAOS:8484` apenas na rede local de confiança.

> Na v0.4 já não é necessário montar `/DATA/AppData/MrStore_webhost/app/`: a imagem publicada inclui os ficheiros Python e HTML. Preserva somente o volume persistente `/data`. **Não inicies duas versões a controlar os mesmos dados/contendores ao mesmo tempo.**

## Testes

```bash
python -m unittest discover -s tests -v
python -m py_compile app/server.py
# Requer Docker com permissão de criar/remover contentores e portas livres (não executar num NAS de produção)
docker build -t mrstore_webhost:ci .
python scripts/integration_smoke.py
```

O smoke test real testa o painel e o deploy de quatro tecnologias nas portas 9101–9104, deixando explícita a necessidade de Docker. Não foi possível executar Docker neste ambiente de desenvolvimento; os testes de integração serão executados no GitHub Actions se os runners tiverem Docker e acesso às imagens.

## Compatibilidade e limitações

| Tecnologia | Imagem/execução | Requisitos |
|---|---|---|
| HTML | `nginxinc/nginx-unprivileged:stable-alpine` | `index.html` na raiz |
| PHP | `php:8.3-apache` | `index.php` ou `index.html`; sem extensões extra |
| React/Vite | Node 22 build, depois Nginx | `package.json` com `scripts.build` e `dist/index.html`/`build/index.html` |
| Node.js | `node:22-alpine` | `package.json` com `scripts.start`, `PORT=3000`, rota `/` responde com 2xx/3xx |

- Só a página `/` é testada; autenticação, bases de dados e endpoints secundários precisam de testes específicos.
- O painel controla um **daemon rootless dedicado**, não o Docker administrativo do NAS. Ainda pode controlar contentores e dados acessíveis ao utilizador rootless; não é seguro para múltiplos utilizadores não confiáveis.
- PHP corre com um processo principal privilegiado, não há quotas globais de armazenamento, backups automáticos, monitorização contínua HTTP, nem isolamento multiutilizador forte.
- Existem pequenas interrupções durante a substituição de portas; o rollback cobre falhas de HTTP no arranque e algumas interrupções da execução, mas não garante recuperação após todas as falhas de energia ou crashes posteriores.
- O editor suporta UTF-8 até 1 MB; os ZIPs são limitados a 50 MB comprimidos, 150 MB descomprimidos e 2.500 ficheiros. Não implementa domínios, HTTPS automático nem MariaDB.
- Antes de usar em servidores com websites importantes, valida todo o fluxo numa máquina Docker de teste e depois no ZimaOS.

Ver `docs/ROOTLESS_SETUP.md`, `docs/CHECKLIST_ZIMAOS.md` e `docs/ZIMAOS_ACCEPTANCE_RESULT.md` para migração, diagnóstico e aceitação física.
