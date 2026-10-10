# MrStore_webhost v0.3 — Alojamento web para ZimaOS

Painel em português para publicar **HTML, PHP, React/Vite e Node.js** em contentores Docker independentes. O painel inclui uma ligação direta para o **catálogo completo de aplicações MrStore** em https://mrpiracy94.github.io/MrStore/, sem copiar ou filtrar a listagem. Continua a ser um gestor de websites e não um instalador universal de apps Docker.

> **Estado: versão experimental para uso numa LAN de confiança.** A execução em ZimaOS físico ainda não está validada. O acesso a `/var/run/docker.sock` concede privilégios administrativos sobre o host; **não exponhas o painel diretamente à Internet.**

## Novidades da v0.3

- **HTTP readiness:** antes de parar o website antigo, inicia a nova release num contentor sem porta publicada e verifica HTTP internamente. Após a troca de portas, repete a verificação HTTP. Códigos 2xx/3xx são considerados prontos; uma rota `/` que devolva 404, 401 ou 500 é considerada falha. Para uma API sem rota `/`, cria uma rota inicial saudável.
- **Recuperação:** mantém o contentor anterior até a nova versão responder, escreve um marcador persistente de publicação em `sites.json` e recupera publicações interrompidas no arranque do painel. Não é recuperação transacional para todo e qualquer cenário de falha, nem zero downtime.
- **Logs:** histórico de publicação por website, mensagens de erro e logs do contentor no painel; jornal limitado a 2 MB antes de uma rotação simplificada.
- **Docker CLI sem `apk add` no arranque:** o `Dockerfile` copia um Docker CLI durante a construção. A instalação via importação do ZimaOS passa a usar uma imagem GHCR preconstruída **apenas após** a workflow `CI and container release` ter passado e a imagem estar publicamente acessível no GHCR.
- **Segurança de rede:** `docker-compose.yml` publica a porta do painel e as portas dos sites apenas em `127.0.0.1` por omissão. Abre para a LAN de forma intencional quando precisares. A configuração `zimaos-compose.yml` publica no LAN para acesso direto e deve ficar atrás de firewall/VPN.
- **CI:** testes Python e JavaScript, integração com Docker real para HTML, PHP, Node e React, e publicação de imagem AMD64/ARM64 no GHCR **depois dos testes passarem**. A existência do workflow não prova que já tenha executado com sucesso.

## Instalar via Docker Compose (recomendado para primeiro teste)

1. Faz download/clona este repositório num host com Docker e Compose. Confirma que a porta 8484 e 9101–9200 estão livres.
2. Copia `.env.example` para `.env`, define `WEBHOST_ADMIN_PASSWORD` única de pelo menos 12 caracteres, confirma o valor absoluto de `WEBHOST_DATA_DIR` e, se fores usar acesso LAN, define **explicitamente** `WEBHOST_PANEL_BIND_IP` e `WEBHOST_SITE_BIND_IP` com o IP LAN do host.
3. Executa `docker compose up -d --build` e consulta os logs com `docker compose logs -f`.
4. Abre `http://127.0.0.1:8484` no próprio host (ou `http://IP_LAN:8484` se ativares acesso LAN). Usa uma VPN ou túnel SSH para acesso remoto.

Os websites criados terão portas 9101–9200, também associadas ao `WEBHOST_SITE_BIND_IP` definido. Numa instalação com bind a `127.0.0.1`, outras máquinas não conseguem alcançar os sites diretamente. A imagem local constrói-se durante a instalação, mas **não precisa de descarregar Docker CLI a cada arranque**.

## Instalar pelo importador do ZimaOS

1. Abre as execuções do GitHub Actions e confirma que `CI and container release` terminou sem erros e publicou `ghcr.io/mrpiracy94/mrstore_webhost:0.3.0` para AMD64/ARM64.
2. Confirma que o pacote GHCR está **público** (a publicação num repositório público não garante visibilidade pública automática do pacote). Se a imagem não puder ser descarregada anonimamente, utiliza a instalação por terminal/Compose.
3. Edita `zimaos-compose.yml`: **substitui** `ADMIN_PASSWORD`, confirma a pasta `/DATA/AppData/MrStore_webhost/data`, as portas e o acesso LAN. Faz backup dos dados da v0.2 antes de atualizar.
4. Importa o ficheiro `zimaos-compose.yml` em **Aplicação personalizada → Importar Docker Compose**.
5. Abre o painel em `http://IP_DO_ZIMAOS:8484` apenas na rede local de confiança.

> Na v0.3 já não é necessário montar `/DATA/AppData/MrStore_webhost/app/`: a imagem publicada inclui os ficheiros Python e HTML. Preserva somente o volume persistente `/data`. **Não inicies duas versões a controlar os mesmos dados/contendores ao mesmo tempo.**

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
- O painel ainda dispõe do socket Docker; isso mantém risco equivalente a permissões de administrador, apesar de `cap_drop`, `read_only` e a escuta local. Isolar o daemon num host dedicado ou introduzir um serviço de deployment com controlos restritivos exigirá trabalho adicional.
- PHP corre com um processo principal privilegiado, não há quotas globais de armazenamento, backups automáticos, monitorização contínua HTTP, nem isolamento multiutilizador forte.
- Existem pequenas interrupções durante a substituição de portas; o rollback cobre falhas de HTTP no arranque e algumas interrupções da execução, mas não garante recuperação após todas as falhas de energia ou crashes posteriores.
- O editor suporta UTF-8 até 1 MB; os ZIPs são limitados a 50 MB comprimidos, 150 MB descomprimidos e 2.500 ficheiros. Não implementa domínios, HTTPS automático nem MariaDB.
- Antes de usar em servidores com websites importantes, valida todo o fluxo numa máquina Docker de teste e depois no ZimaOS.

Ver `docs/AUDITORIA.md` e `docs/CHECKLIST_ZIMAOS.md` para informações adicionais sobre migração e segurança.
