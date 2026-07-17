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

## Subagents (`.claude/agents/`)
- **qa-speech-analytics** — despacha uma investigação de QA/Speech Analytics de ponta a ponta
  (carrega a skill, aplica os guardrails de rigor, devolve relatório com trecho-prova).
  Use para "por que não fechou", A/B do fornecedor, NO_MATCH/ASR, recortes temáticos, run diário.
