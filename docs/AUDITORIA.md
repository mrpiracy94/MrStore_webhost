# Auditoria da v0.1 → v0.2

## Problemas identificados e ações

| Achado | Efeito potencial na v0.1 | Tratamento v0.2 |
|---|---|---|
| Substituição direta de `source/` durante upload | Sites em execução podiam perder ficheiros | Publicações usam snapshots isolados em `releases/`; o ZIP altera apenas `source/` |
| Apagar contentor antes do build/arranque novo | Erro de build podia interromper o site em produção | Build primeiro, manter contentor antigo até à promoção; rollback best-effort |
| Sem editor de ficheiros | Requeria ZIP para qualquer alteração | Gestor visual para ficheiros de texto UTF-8 até 1 MB |
| API aceitava POSTs sem prova anti-CSRF além de Origin opcional | Proteção incompleta contra pedidos cross-site | Header não simples obrigatório + verificação de Origin quando presente |
| Comandos de instalação Docker dependentes de `apk add` no boot | Arranque podia falhar sem rede | Mantida opção `Dockerfile` para imagem pré-construída; método de importação continua a ter dependência de rede |
| Docker socket montado no painel | Acesso potencial a root do anfitrião | Risco explicitado; **não solucionado** na v0.2 |
| Sem publicação real verificada em ZimaOS | Compatibilidade não demonstrada | Testes simulados ampliados; **teste no hardware continua pendente** |

## Limitações importantes

- Contentor temporário, paragem e promoção exigem algum downtime; o rollback não cobre falhas de hardware, reinícios durante a troca nem aplicações que falham após o instante do arranque.
- Publicação de sites de terceiros envolve execução arbitrária de PHP, Node e scripts de instalação npm. O isolamento Docker não torna projetos não confiáveis seguros.
- A revisão não é uma auditoria de segurança independente. Não expor à Internet sem um desenho de segurança adicional.
- Se ainda existem contentores publicados com a v0.1, republica cada site uma vez após instalar a v0.2 e antes de alterar o código através do editor.