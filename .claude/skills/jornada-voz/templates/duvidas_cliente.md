# Esqueleto do artefato de dúvidas (`projetos_coral/<chave>/jornada/duvidas_<chave>.html`)

Modelo publicado: a Vale, `https://claude.ai/artifact/BckiYdCq3JuPnFPSdmVucb` (fonte
`projetos_coral/vale-consignado/jornada/duvidas_vale.html`, 18 dúvidas). Publicar como artifact compartilhado por
link; cada republicação mantém a URL.

Cabeçalho: nome do cliente, data da versão, link do board, uma frase do que o material é ("perguntas que travam a
fala da Córa; a resposta muda o que ela diz").

Cada dúvida, numerada e estável (nunca renumerar):

| Campo | Conteúdo |
|---|---|
| **Pergunta** | uma frase, na linguagem do cliente |
| **Por que importa** | o que a Córa faz hoje e o que mudaria |
| **Hoje a Córa diz** | a fala atual, com as variáveis em `[colchetes]` |
| **Se a resposta for A / B** | a fala em cada caso |
| **Onde está no board** | código da caixa + link direto (`...?node-id=<id>`) |
| **Status** | aberta · respondida em dd/mm (resposta) · substituída por nº |

Seções: por bloco do board (abertura · situação 1 · situação 2 · ... · encerramentos · integração). Pergunta do
cliente no canal entra como dúvida nova na seção que ela afeta.

Sem termo interno (SPT, nó, Sinergy, custo). Link do artefato vai ao dossiê.
