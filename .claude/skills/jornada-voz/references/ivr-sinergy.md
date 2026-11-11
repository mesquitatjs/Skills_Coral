# A IVR no padrão da Sinergy

A Sinergy constrói o bot no OCS a partir de um arquivo `.ivr`. Não existe gerador oficial: o `.ivr` é um objeto .NET
serializado (BinaryFormatter, MS-NRBF). Em 06–10/11/2026 montamos o nosso, a partir do `.ivr` da Bull (v8) como
molde de classes. Tudo em `coral-bot/scripts/homologacao/`.

## Peças

| Arquivo | Papel |
|---|---|
| `nrbf_rw.py` | lê e escreve o binário sem perda (round trip da Bull v8: 154.743 bytes idênticos) |
| `ivr_grafo.py` | decodifica o grafo de objetos (`Obj`, `Str`, `Box`, `Arr`, `Nulls`) e o codifica de volta. Regra de ids: fila de objetos; toda referência a objeto já visto consome id, exceto se for o mesmo objeto da referência anterior; struct e enum em linha com id negativo; o id da biblioteca conta |
| `ivr_script.py` | extrator: do `.ivr` para o mapa JSON que a demo executa (é o que permite homologar a conversa do arquivo gerado) |
| `ivr_vale.py` | **gerador da Vale**, molde para o próximo cliente: `CATALOGO` (ids de interação do OCS conhecidos), `DE_PARA` (interação do mapa → nome do catálogo), `SISTEMA` (variáveis que o OCS já tem), `Fabrica` (monta nós, enums, listas e variáveis com as classes do molde), `montar(mapa, classes, cpn, nome)`, `gerar(molde, saida, cpn)` |
| `teste_ivr_vale.py` | confere o arquivo gerado em 4 níveis (abaixo) |

## Como gerar para um cliente novo

1. Copie `ivr_vale.py` para `ivr_<chave>.py`. Troque `MAPA` (o JSON do cliente), `nome` da campanha e o `DE_PARA`
   (cada desfecho do mapa aponta para um nome do `CATALOGO`; o que não existe fica sem id e vira
   `[SINERGY: cadastrar interação, id 0 é provisório]`).
2. Molde e saída no **scratchpad**, nunca no repo (`*.ivr` está no `.gitignore`):
   ```bash
   python scripts/homologacao/ivr_<chave>.py <scratchpad>/ivr/in/bull8.ivr <scratchpad>/ivr/out/<NOME>_v1.ivr --cpn 0
   ```
3. `gerar()` trava se o arquivo carregar `Password=`, `User ID=`, `Data Source=`, `provider_key` ou `api.coralai`.
   `DatabaseConnections` sai vazia.
4. O que o `montar` faz com o mapa: `@telefone` após o mailing (nó 300); "É O CLIENTE" (200/201); "IDENTIDADE
   CONFIRMADA · <situação>" (210–217, interação 2465); um `NodeRedirect` por desfecho (400+) para agrupar as saídas;
   raízes `[1, 7, 10, 20, 3x...]`; o nó 199 grava OUTCOME = `@cod_ocorrencia`, DESFECHO = `@desfecho`, TELEFONE
   = `@telefone`; variáveis descobertas por regex `@nome` no mapa, menos as de `SISTEMA`.
5. Entregue o arquivo ao usuário por `SendUserFile`. O nome segue `NOME_DA_CAMPANHA_vN.ivr`.

## Homologação do nosso lado (`teste_ivr_<chave>.py`)

1. **Formato:** o arquivo gerado é lido de volta por `nrbf_rw` e `ivr_grafo` sem erro, e o round trip é idêntico.
2. **Estrutura/formas:** cada tipo de nó tem os mesmos campos e formas (lista com capacidade, nulos, enums,
   `TestLastVariables`) que o molde; InteractionId e CampaignResultId como `Box(8, 0)` quando provisórios, nunca
   null. Conferir "formas" novas contra o molde: na Vale ficaram 11 sem precedente e todas foram alinhadas.
3. **Conteúdo:** o extrator relê o arquivo e o resultado bate com o mapa nó a nó (tipos, prompts, saídas resolvidas
   até o desfecho, variáveis, campos do mailing, resultado final, interações com id ou 0); nada de `Password=`,
   nem nome do cliente do molde.
4. **Conversa:** o executor da demo (`motor.Sessao(None, pid, mapa=mapa_extraido)`) roda ligações roteirizadas com
   chat falso por cima do mapa **extraído do `.ivr`**, uma por situação, e chega ao desfecho certo.
5. O mapa extraído (`demo_voz/ref/mapa_<chave>_ivr.json`) é versionado e entra na **matriz** do workflow do teste
   com o modelo: a mesma conversa tem de passar no mapa da demo e no da IVR.

Saída esperada do teste: `tudo ok`.

## O que fica com a Sinergy (vai no chamado)

- importar o `.ivr` no editor do OCS e abrir a campanha de homologação (`cpnId`);
- cadastrar as interações que não existem no catálogo (listadas por `gerar()` em "interações para a Sinergy
  cadastrar") e trocar o id provisório 0;
- os ids de resultado da campanha (OUTCOME / DESFECHO / TELEFONE);
- o registro do acordo (`NodeWebServiceRequestJson` marcado `[SINERGY: URL, cabeçalhos e corpo a definir com a
  integração]`): depende da integração com o sistema do cliente (na Vale, CobranSaaS pelo Renato);
- voz TTS, silêncio e timeouts se o cliente pedir diferente do padrão.

## Chamado e plano de testes

- Chamado: molde `projetos_coral/bull/CHAMADO_SinergyTech_Jornada_Bull.md`. Anexos: o `.ivr`, o link do board (só
  a seção 3 interessa a eles), a lista de interações a cadastrar e os marcadores `[SINERGY: ...]`.
- Plano de homologação: molde `projetos_coral/bull/PLANO_TESTES_Homologacao_Voz.md` e o checklist clicável da Bull
  (`bull/_homologacao_voz_bull.html`). Blocos: conformidade (bloqueante) · fluxo e oferta por situação · objeções ·
  transbordo para o WhatsApp · tabulação · qualidade de conversa · buracos conhecidos. Cada caso: o que falar, o SPT
  esperado, o que reprova.
- **Antes da primeira ligação:** conferir numeração board × mapa × bot (na Bull, 4 nós tinham número diferente
  entre board e doc e a tabulação sairia errada). Com o gerador como fonte única isso não deveria acontecer; confira
  mesmo assim.
- Prometer humano ao vivo reprova. "Transbordo" é WhatsApp.
