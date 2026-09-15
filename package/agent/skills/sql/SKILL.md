-----------------------------------------------------
name: sql
description: Orienta descoberta de schema, geração, validação e correção de SQL analítico read-only.
-----------------------------------------------------

# Objetivo

Produzir consultas SQLite corretas e verificáveis usando exclusivamente o schema realmente
descoberto no banco do usuário.

# Procedimento

1. Quando o schema relevante ainda não estiver confirmado, use a ação `inspect_schema` da Tool
   `database` antes de escrever SQL.
2. Use somente tabelas e colunas observadas no schema retornado.
3. Gere apenas SQL read-only compatível com SQLite, iniciando por `SELECT` ou `WITH`.
4. Explicite filtros de período, status, canal, categoria e demais critérios necessários para
   reproduzir a pergunta de negócio.
5. Em agregações, valide a granularidade e o risco de duplicação provocado por joins.
6. Quando uma consulta falhar, use o erro retornado pela Tool como evidência para corrigir a SQL
   e tente novamente quando ainda houver motivo para continuar.
7. Quando o resultado for insuficiente para a conclusão, faça outra consulta direcionada em vez
   de inferir valores ausentes.

# Validação

Antes de considerar uma consulta suficiente, verifique:

- se as tabelas e colunas existem;
- se joins utilizam chaves coerentes;
- se filtros representam a pergunta do usuário;
- se `COUNT`, `DISTINCT`, médias e agrupamentos estão na granularidade correta;
- se datas e períodos estão sendo comparados no formato armazenado;
- se o resultado responde à etapa atual da investigação.

# Restrições

Nunca execute INSERT, UPDATE, DELETE, DROP, ALTER, CREATE ou qualquer operação de escrita.
