# Skills_Coral

Skills e subagents duráveis da CoralAi (Claude Code), versionados em git para não se
perderem entre sessões. Auto-descobertos via `.claude/skills/` e `.claude/agents/`.

## Skills (`.claude/skills/`)
- **collection-pilot-model** — gera planilhas `.xlsx` de projeção de remuneração para
  pilotos de cobrança (bandas/produtos, 3 cenários, custos, Lucro Presumido, margem,
  modelo híbrido piso+fee, aba Simulador).
- **qa-speech-analytics** — QA & Speech Analytics do voice bot de cobrança (HIB Principia ·
  OCS Sinergytech): coleta de logs/áudio, parsing determinístico, métricas de funil/ASR,
  controles de rigor, LGPD, entregáveis. KB completa em `references/knowledge-base.md`.

- **implantacao-cliente** — implanta um CLIENTE NOVO na stack da Coral de ponta a ponta:
  questionário (identidade, remuneração, discador, telecom, mailing, dados, mensageria,
  painéis, alertas) → ficha → pacote de implantação aprovado → controles, automações,
  painéis e alertas nos 3 repositórios, em ondas → verificador de cobertura (gate) →
  go-live com checagens agendadas. Construída a partir da implantação da Bull (set–out/2026).
- **jornada-voz** — cria a jornada de voz da Córa para um cliente novo no modelo da Vale Consignado
  (out–nov/2026): leitura das fontes → pesquisa e jornada por situação → board no FigJam (3 seções, um cenário
  por caixa, variáveis em `[colchetes]`) → regras de fala e ofertas fixas → artefato de dúvidas ligado às caixas →
  demo com link de prospect (gerador de mapa, prompts no formato da Sinergy, personas, testes sem e com o modelo) →
  `.ivr` no padrão da Sinergy homologado do nosso lado → chamado e plano de testes. Moldes de prompt em `templates/`.
- **ucc-precificacao** — precifica cliente no modelo UCC (planilha interna → proposta).
- **deck-comercial** — *mora no `coral-engineering/guizera_skills`* (`.claude/skills/deck-comercial/`,
  autocontida: gerador, layout, logos e fichas). Não duplicar aqui (fonte única). Monta a apresentação comercial
  da Coral para um cliente novo no layout oficial.

## Subagents (`.claude/agents/`)
- **qa-speech-analytics** — despacha uma investigação de QA/Speech Analytics de ponta a ponta
  (carrega a skill, aplica os guardrails de rigor, devolve relatório com trecho-prova).
  Use para "por que não fechou", A/B do fornecedor, NO_MATCH/ASR, recortes temáticos, run diário.
