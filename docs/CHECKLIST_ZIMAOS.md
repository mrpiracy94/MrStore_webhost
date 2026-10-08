# Checklist de validação ZimaOS — v0.3

- [ ] Confirmar backup de `/DATA/AppData/MrStore_webhost/data` e acesso a versão anterior.
- [ ] Confirmar ZimaOS suporta a imagem AMD64/ARM64 publicada no GHCR.
- [ ] Confirmar sucesso do workflow CI e visibilidade pública do pacote GHCR.
- [ ] Alterar password de administração, garantir que firewall não expõe 8484 e 9101–9200 à Internet.
- [ ] Confirmar caminhos no host ZimaOS e direitos de escrita em `/DATA/AppData/MrStore_webhost/data`.
- [ ] Validar instalação, login, criação, upload ZIP e publicações HTML/PHP/React/Node.
- [ ] Editar ficheiros sem afetar versão online; atualizar e confirmar que alterações estão acessíveis.
- [ ] Testar erro HTTP (404/500 na rota `/`) e recuperação para a última release.
- [ ] Simular interrupção do painel durante publicação num ambiente de teste, reiniciar e validar estado.
- [ ] Inspecionar histórico de publicação no painel e logs Docker.
- [ ] Verificar alterações com URL LAN nas portas reais e reset após reiniciar o NAS.
- [ ] Executar revisão de segurança e definir backups automáticos fora do NAS.
