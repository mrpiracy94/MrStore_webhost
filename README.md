# MrStore_webhost 0.2 — Painel de alojamento para ZimaOS

**Protótipo funcional para uso pessoal e LAN. Não é um painel de produção, nem foi testado num dispositivo ZimaOS real.** Gere websites HTML/CSS/JS, PHP básico, React/Vite estático e Node.js (`npm start`) em contentores Docker independentes.

## Novidades da v0.2

- **Gestor de ficheiros:** consultar, criar, editar e apagar ficheiros de texto no navegador (até 1 MB por ficheiro). Abre **Ficheiros** no cartão do website; edita e clica em **Guardar alterações**. O website só muda quando carregares em **Publicar**.
- **Publicação por versões:** cada publicação cria uma cópia isolada em `data/sites/<slug>/releases/<versão>`; o ZIP e o editor modificam apenas `source/`.
- **Menos interrupções:** valida os ficheiros e executa o build antes de parar o contentor antigo; em determinados erros de arranque tenta repor o anterior. Durante a troca do contentor há uma breve indisponibilidade. Não existe garantia de rollback em falhas de máquina, reinícios ou erros de aplicação após arrancar.
- **Proteção CSRF:** API exige `X-MrStore_webhost-Request: 1` em pedidos POST e valida `Origin` quando presente. O painel acrescenta o cabeçalho automaticamente.
- **Verificações adicionais:** bloqueio de caminhos fora da pasta do website, limitação de edição e testes para falhas de atualização.

## Instalação com o importador do ZimaOS

1. Descompacta o ZIP no teu computador.
2. No ZimaOS, cria as pastas `/DATA/AppData/MrStore_webhost/app` e `/DATA/AppData/MrStore_webhost/data` (confirma que `/DATA` é o teu volume correto).
3. Copia `app/server.py` e `app/index.html` do pacote para `/DATA/AppData/MrStore_webhost/app/`.
4. Edita **`zimaos-compose.yml`** e define uma password única de pelo menos 12 caracteres no campo `ADMIN_PASSWORD`. Se alterares o caminho de dados, atualiza *tanto* `HOST_DATA_DIR` como o volume `/data`.
5. No painel do ZimaOS, importa o conteúdo editado do `zimaos-compose.yml` como aplicação Docker Compose personalizada e instala.
6. Abre `http://IP_DO_ZIMAOS:8484` pela rede local.

**Atenção:** o método de importação utiliza `python:3.12-alpine` e descarrega `docker-cli` no arranque, exigindo ligação à Internet em cada arranque enquanto essa dependência não estiver em cache. Para evitar isso, utiliza a alternativa abaixo.

## Instalação por terminal/SSH

1. Copia toda a pasta `MrStore_webhost` para o teu ZimaOS ou Linux Docker.
2. Copia `.env.example` para `.env`, escolhe `WEBHOST_ADMIN_PASSWORD` e confirma o caminho absoluto `WEBHOST_DATA_DIR`.
3. Na pasta do projeto, executa `docker compose up -d --build`.
4. Abre `http://IP_DO_ZIMAOS:8484`.

O método por terminal pode não criar automaticamente o ícone na App Store do ZimaOS. O `Dockerfile` instala `docker-cli` ao construir a imagem e não depende do `apk add` em cada reinício.

## Migração de versões anteriores (ZimaWebHost v0.1/v0.2)

Esta publicação foi renomeada para **MrStore_webhost**. A instalação nova utiliza `/DATA/AppData/MrStore_webhost/` e o contentor `mrstore_webhost-panel` por omissão. **Não é uma atualização automática in-place** da marca anterior: ao migrar, faz backup de `/DATA/AppData/ZimaWebHost/data` e decide se queres copiar os dados para `/DATA/AppData/MrStore_webhost/data` antes do arranque. Não executes as duas versões simultaneamente na mesma porta 8484 nem permitas que ambas controlem os mesmos websites. A migração real não foi testada em ZimaOS.

## Utilização

1. Clica em **Novo website**, indica nome, identificador e tecnologia.
2. Envia o teu projeto em ZIP; ou abre **Ficheiros** e cria `index.html`, `index.php`, `package.json` etc.
3. Clica em **Publicar**. O site fica numa porta da gama 9101–9200.
4. Consulta **Logs** quando surgir um erro. Usa **Parar** ou **Eliminar** quando necessário.

| Tecnologia | Requisito | Execução |
|---|---|---|
| HTML / CSS / JS | `index.html` | Nginx sem privilégios |
| PHP | `index.php` ou `index.html` | PHP 8.3 e Apache; extensões opcionais não instaladas |
| React / Vite | `package.json` com `scripts.build`; cria `dist/index.html` ou `build/index.html` | Node 22 para build, Nginx para servir |
| Node.js | `package.json` com `scripts.start`; escuta `0.0.0.0` na porta 3000 / `PORT` | Node 22, `npm start` |

Os ZIPs de teste encontram-se em `examples/zips/`. Next.js SSR, Laravel, WordPress, PHP com dependências adicionais e aplicações que precisem de volumes de escrita não têm configuração automática. Para Node/React, as dependências são instaladas com `npm ci`/`npm install` no Docker; a origem do projeto deve ser confiável.

## Segurança e limitações — leitura obrigatória

- **O painel tem acesso ao socket Docker (`/var/run/docker.sock`). Isto dá controlo administrativo sobre o host.** Não publiques a porta 8484 na Internet. Utiliza a aplicação apenas num NAS de confiança e numa rede local controlada.
- O painel utiliza HTTP local; a password e sessão não estão cifradas em trânsito. Para acesso remoto, prefere uma VPN ou HTTPS configurado por um administrador. Nunca uses HTTP em redes não confiáveis. HTTPS não vem pré-configurado.
- Os websites publicados usam portas TCP locais entre `9101` e `9200`, geralmente acessíveis na rede se o firewall permitir. Não são automaticamente protegidos por autenticação.
- PHP usa uma imagem Apache com processo principal de root. Não alojes código PHP não confiável. Não há isolamento de segurança equivalente a um alojamento multiutilizador.
- Não existem quotas globais de disco para os websites nem um backup automático. São guardadas a release atual e a anterior; faz backup da pasta `data`.
- A recuperação automática cobre apenas alguns erros de troca de contentores. **Não há zero downtime, verificação HTTP de saúde, nem recuperação assegurada de crashes posteriores.**
- Upload ZIP até 50 MB, no máximo 2500 entradas e 150 MB descomprimidos; editor apenas para ficheiros UTF-8 até 1 MB. Rejeitam-se ZIPs com links simbólicos, caminhos de escape e ficheiros especiais.
- Não inclui domínios, HTTPS automático, Git, SSL, MariaDB, backups ou contas múltiplas. Essas funcionalidades ainda estão por implementar.
- ZimaOS usa tipicamente portas de sistema próprias: evita reservar 80 e 443 sem verificar os serviços existentes.

## Resolução de problemas

- Painel não inicia: confirma `ADMIN_PASSWORD`, a montagem `/data`, a existência de `app/server.py` e os logs do contentor `mrstore_webhost-panel`.
- Erro Docker: confirma `/var/run/docker.sock` e permissões do contentor.
- Porta ocupada: vê os logs de Docker e liberta a porta do site, ou ajusta a configuração no host (edição visual de portas ainda não disponível).
- React/Node não arranca: verifica `package.json`, os scripts npm, o acesso à Internet do builder e os logs após a publicação.
- A publicação mostrou sucesso mas o site não carrega: consulta **Logs**. O teste de arranque apenas confirma que o contentor está a correr, não que a aplicação HTTP está saudável.

## Verificação

- Testes unitários e HTTP locais com Docker simulado: `python -m unittest discover -s tests -v`.
- JavaScript verificado sintaticamente com Node.js; YAML verificado sintaticamente com PyYAML.
- **Sem teste de publicação Docker real neste ambiente.** Antes de instalar no NAS de produção, testa numa máquina Docker de desenvolvimento.

Consulta também `docs/AUDITORIA.md` para os problemas identificados na v0.1, o tratamento aplicado e as limitações remanescentes.

## Código fonte e publicação

Esta aplicação está publicada no repositório independente [`mrpiracy94/MrStore_webhost`](https://github.com/mrpiracy94/MrStore_webhost), separado da MrStore. O projeto inclui o painel (`app/`), configuração Docker, documentação de auditoria (`docs/`), testes unitários (`tests/`) e exemplos (`examples/`). O ficheiro `.env` privado e a pasta de dados não devem ser publicados. O projeto não está validado em ZimaOS físico nem preparado para exposição direta à Internet.