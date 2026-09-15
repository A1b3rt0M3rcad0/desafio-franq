-----------------------------------------------------
name: planning
description: Planeja investigações analíticas e decompõe perguntas de negócio em etapas verificáveis.
-----------------------------------------------------

# Objetivo

Transformar uma pergunta de negócio em uma sequência mínima e verificável de investigação,
sem inventar dados, schema ou conclusões.

# Quando usar

Use esta Skill quando a solicitação exigir mais de uma etapa, combinar informações diferentes,
resolver dependências entre consultas ou decidir qual evidência precisa ser coletada antes da
resposta final.

# Procedimento

1. Identifique exatamente o que o usuário quer saber e quais métricas, dimensões, filtros e
   períodos estão envolvidos.
2. Separe fatos já disponíveis de informações que ainda precisam ser verificadas.
3. Determine quais operações podem ser executadas de forma independente e quais dependem de
   resultados anteriores.
4. Prefira o menor conjunto de consultas capaz de responder à pergunta com segurança.
5. Reavalie o plano quando uma Tool retornar erro, ausência de dados ou um resultado que torne
   uma etapa anterior inválida.
6. Encerre a investigação quando já houver evidência suficiente para uma resposta confiável.

# Regras

- Não invente tabelas, colunas, relações ou valores.
- Não execute consultas apenas por precaução se elas não contribuírem para a conclusão.
- Quando houver ambiguidade material, investigue antes de assumir.
- O plano é operacional; não exponha chain-of-thought ao usuário.
