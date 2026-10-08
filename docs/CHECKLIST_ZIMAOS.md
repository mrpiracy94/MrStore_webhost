# Checklist de validação em ZimaOS (a executar no equipamento)

O pacote foi validado com testes HTTP locais e com Docker simulado. Antes de instalares em definitivo:

1. Faz backup de `/DATA/AppData/MrStore_webhost/data` (se já existe versão anterior).
2. Confirma acesso à Internet na primeira instalação do painel e para descarregar imagens Docker.
3. Abre `http://IP_ZIMAOS:8484`, inicia sessão e cria um website HTML com `examples/zips/exemplo-html.zip`.
4. Publica; verifica o acesso a `http://IP_ZIMAOS:9101/` e os logs Docker.
5. Abre **Ficheiros**, edita `index.html` e guarda; confirma que o site publicado continua inalterado **até** clicares em **Publicar**.
6. Publica novamente; confirma que a alteração aparece no navegador.
7. Repete com `examples/zips/exemplo-php.zip`, `exemplo-react.zip` e `exemplo-node.zip` (as portas dependem da ordem de criação).
8. Simula uma publicação HTML inválida, removendo temporariamente `index.html` do projeto. Confirma que o painel apresenta erro e que a última versão publicada continua disponível.
9. Valida **Parar**, **Logs** e **Eliminar** num site descartável.
10. Confirma as regras da firewall, volumes de armazenamento e que **a porta 8484 não está acessível publicamente**.

Não executar testes destrutivos em websites importantes sem backup. A recuperação automática não substitui uma estratégia de backup.