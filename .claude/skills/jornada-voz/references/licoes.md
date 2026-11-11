# Lições da Vale (out–nov/2026)

Ler antes de desenhar o próximo. Cada uma custou pelo menos uma rodada.

## Desenho

1. **Pesquisa antes da fala.** A jornada do demitido só ficou certa depois de ler o manual do Crédito do Trabalhador:
   o FGTS não abate sem garantia, o 13º não desconta, o RH não muda o limite dos 35%. Fala escrita de cabeça estava
   errada em três pontos (`bull/CREDITO_DO_TRABALHADOR_Mecanica.md` §7 lista os mesmos erros na Bull).
2. **Datas próximas primeiro, dia do salário nunca.** A versão 1 oferecia o dia do salário; o usuário trocou por
   datas curtas e o cliente (Doug) fechou em ofertas fixas. Pergunta "quando você recebe" abre negociação que a
   Córa não pode fazer.
3. **Um cenário por caixa.** O board de C/D/E nasceu com "à vista ou parcelado" na mesma caixa. Quebrar depois de
   publicado custou uma reorganização inteira da seção 3. Nasça quebrado.
4. **Variável com um nome só.** `(data)`, `{data_curta}`, `[data_max]` conviveram no mesmo board. Padronizar depois
   exigiu varredura em 247 caixas.
5. **Valor abaixo do mínimo não encerra.** A primeira versão encerrava a ligação; a regra certa é enquadrar na
   oferta mais próxima e seguir.
6. **Seções de rascunho confundem o cliente.** Sete seções viraram três antes de mandar o link. O cliente vê uma
   versão só.
7. **Nome de etapa em linguagem de gente.** "R+7" virou "7 dias do novo emprego"; "contrato novo/antigo" virou
   "com/sem garantia do FGTS". Revisão final lendo como o cliente lê.

## Demo e prompts

8. **O modelo lê "amanhã" como outra data e repete a pergunta da data quando o cliente aceita sem escolher.** As
   duas regras entraram no bloco DATAS e nas checagens.
9. **"Então fica pra sábado. Então fica assim"**: confirmação com a data repetida e dois "Então". Regra de
   confirmação direta + checagem automática.
10. **Checagem por string fixa quebra com fala boa.** "posso mandar" não casava com "prefere que eu mande". Regex
    com as formas aceitas.
11. **O avaliador precisa saber a situação do contrato.** Marcava violação do saldo ao demitido com rescisão abatida
    e ao afastado. `_situacao_vale(d)` no contexto do avaliador.
12. **O filtro de conteúdo do provedor reserva barra a fala de crise.** `_resposta_crise` devolve a fala fixa e a
    saída de CRISE.
13. **Teste com o modelo em duas rodadas.** Uma passa por sorte.
14. **Crédito da API acaba.** `429 no credits remaining` não é defeito; registrar e redisparar.

## IVR

15. **O `.ivr` é .NET BinaryFormatter.** Decodificar exigiu acertar a regra de ids do ObjectIDGenerator (toda
    referência repetida consome id; o id da biblioteca conta). Prova: round trip idêntico byte a byte.
16. **Classe certa pelo nome exato.** `cls()` escolhia a `List`1` em vez da struct de mesmo prefixo; o `KeyError
    '<Id'` vinha da ordem de `lstrip`/`replace`. Teste de "formas" contra o molde pega isso.
17. **Trava de credencial por padrão de valor, não de nome.** `Password` batia no membro
    `ClientCertificatePassword`; a trava é `Password=`.
18. **Na IVR o OUTCOME é o SPT, não o nome do desfecho.** O teste lê `@desfecho` quando OUTCOME é numérico.
19. **O molde nunca entra no repo.** Carrega senha de banco e chave de API. `*.ivr` no `.gitignore`.
20. **O que é da Sinergy fica marcado, não inventado.** `cpnId`, ids de interação, ids de resultado, registro do
    acordo: `[SINERGY: ...]` na descrição do nó e lista no fim do `gerar()`.

## Processo

21. **Canal do cliente antes de responder.** As perguntas do Doug no `#vale-consignado` mudaram o modelo de
    negociação; ler o canal é a Fase 0.
22. **Resposta ao cliente é rascunho.** Nunca postar; entregar ao usuário.
23. **Share do Figma não é automático.** Liberar antes de mandar o link.
24. **Dúvida tem endereço.** Cada dúvida liga à caixa que ela trava; dúvida respondida ganha resposta e data, não some.
