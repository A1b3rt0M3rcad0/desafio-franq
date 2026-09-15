-----------------------------------------------------
name: visualization
description: Decide autonomamente quando resultados analíticos devem ser apresentados como tabela ou gráfico e declara a apresentação estruturada.
-----------------------------------------------------

# Objetivo

Escolher a representação visual que melhor comunica os dados reais encontrados durante a
investigação e, quando uma apresentação agregar valor, declará-la com a Tool `present_result`.

A visualização vem depois da análise. Primeiro obtenha e valide os dados necessários; depois
decida como apresentá-los.

# Responsabilidades

- Decida se uma visualização realmente melhora a resposta.
- Escolha o tipo de apresentação de acordo com a estrutura e a intenção analítica dos dados.
- Use somente valores já obtidos por Tools nesta execução.
- Garanta que os dados estejam na granularidade final antes de apresentá-los.
- Chame `present_result` para registrar a tabela ou o gráfico que acompanhará a resposta final.
- Não escreva código Python, Matplotlib ou Seaborn. A interface é responsável pela renderização.

# Seleção

## Sem visualização

Não chame `present_result` quando um valor único ou uma conclusão textual curta comunicar o
resultado melhor do que uma tabela ou gráfico. Não force visualizações apenas porque a
capacidade existe.

## Tabela

Use `table` quando a leitura precisa dos valores for mais importante do que a comparação visual,
por exemplo listas detalhadas, rankings com valores exatos ou resultados com várias colunas.

## Barras

Use `bar` para comparar categorias discretas, como canais, estados, produtos, categorias ou
grupamentos equivalentes. Também é apropriado para rankings.

Os dados devem chegar previamente agregados no grão que será exibido. Não envie várias linhas
da mesma categoria esperando que a interface calcule soma, contagem ou média.

## Linha

Use `line` para séries temporais ou outras sequências em que a ordem do eixo X tenha significado.
Os dados devem estar na ordem analítica correta antes da apresentação, preferencialmente já
ordenados na consulta que os produziu.

Não use linha apenas para conectar categorias sem relação ordinal.

## Dispersão

Use `scatter` para representar relação entre duas medidas numéricas. Os campos X e Y devem ser
numéricos e o gráfico deve ajudar a investigar associação, concentração ou dispersão.

# Séries e agrupamentos

- Use múltiplos campos em `y` somente quando as séries compartilham unidade e escala comparáveis.
- Use `hue` para um agrupamento categórico adicional quando sua cardinalidade for pequena e a
  comparação continuar legível.
- Não combine múltiplos campos `y` com `hue` na mesma apresentação.
- Para `scatter`, use exatamente um campo `y`.
- Use `orientation: horizontal` apenas para barras quando isso melhorar a leitura das categorias.

# Granularidade

A Tool de dados deve produzir o mesmo grão necessário para a visualização. Cálculos de negócio,
agregações, contagens, médias e agrupamentos pertencem à investigação/SQL, não ao renderer.

Exemplo: para comparar reclamações não resolvidas por canal, obtenha uma linha final por canal
com a contagem calculada no SQL e só então declare o gráfico de barras.

# Contrato de apresentação

Ao chamar `present_result`, envie:

- `data.columns`: nomes dos campos presentes nos dados.
- `data.rows`: linhas reais que serão apresentadas.
- `visualization.type`: `table`, `bar`, `line` ou `scatter`.
- `visualization.title`: título de negócio curto quando útil.
- `visualization.x`: campo do eixo X para gráficos.
- `visualization.y`: um ou mais campos numéricos de valores.
- `visualization.hue`: agrupamento opcional, quando aplicável.
- `visualization.x_label` e `visualization.y_label`: rótulos amigáveis opcionais.
- `visualization.orientation`: `vertical` por padrão ou `horizontal` para barras.

# Validação antes de apresentar

Antes de chamar `present_result`, confirme:

1. os valores vieram de resultados reais desta execução;
2. todos os campos declarados existem nos dados;
3. os campos de valores usados em gráficos são numéricos;
4. a granularidade já corresponde à visualização desejada;
5. o tipo escolhido responde melhor à pergunta do que as alternativas;
6. a visualização solicitada explicitamente pelo usuário é respeitada quando compatível com os
   dados.

Se `present_result` rejeitar a especificação, use a mensagem de erro para corrigir os dados ou a
configuração e tente novamente. Nunca invente valores para fazer a apresentação passar na
validação.
