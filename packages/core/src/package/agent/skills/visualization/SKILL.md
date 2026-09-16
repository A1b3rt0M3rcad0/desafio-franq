-----------------------------------------------------
name: visualization
description: Decide quando usar tabelas ou gráficos e como preparar dados para visualizações inline na resposta final.
-----------------------------------------------------

# Objetivo

Escolher a representação visual que melhor comunica os dados reais encontrados durante a
investigação e preparar evidências compactas para que a resposta final possa intercalar texto e
uma ou mais visualizações.

A visualização vem depois da análise. Primeiro obtenha e valide os dados necessários; depois
decida como apresentá-los.

# Responsabilidades

- Decida se uma visualização realmente melhora a resposta.
- Escolha o tipo de apresentação de acordo com a intenção analítica e a estrutura dos dados.
- Use somente valores já obtidos por Tools nesta execução.
- Garanta que os dados estejam na granularidade final antes da resposta.
- Quando houver mais de um ponto analítico distinto, considere múltiplas visualizações, uma para
  cada evidência que realmente se beneficie de representação visual.
- Não escreva código Python, Matplotlib ou Seaborn. A interface é responsável pela renderização.

# Seleção

## Sem visualização

Não force gráficos para valores únicos ou conclusões curtas que sejam mais claras em texto.

## Tabela

Use `table` quando a leitura precisa dos valores for mais importante do que a comparação visual,
por exemplo listas detalhadas, rankings com valores exatos ou resultados com várias colunas.

## Barras

Use `bar` para comparar categorias discretas, como canais, estados, produtos, categorias ou
outros agrupamentos equivalentes. Também é apropriado para rankings.

Os dados devem chegar previamente agregados no grão exibido. Não deixe para a interface somar,
contar, calcular média ou resolver granularidade.

## Linha

Use `line` para séries temporais ou outras sequências em que a ordem do eixo X tenha significado.
Os dados devem estar na ordem analítica correta antes da apresentação, preferencialmente já
ordenados na consulta que os produziu.

Não use linha apenas para conectar categorias sem relação ordinal.

## Dispersão

Use `scatter` para representar relação entre duas medidas numéricas. Os campos X e Y devem ser
numéricos e o gráfico deve ajudar a investigar associação, concentração ou dispersão.

# Múltiplas visualizações

Uma resposta pode precisar de mais de um gráfico. Use visualizações separadas quando elas
sustentarem perguntas ou conclusões diferentes, por exemplo uma série temporal para evolução e
um gráfico de barras para composição por canal.

Não repita o mesmo dado em vários gráficos sem necessidade. Prefira uma narrativa em que cada
gráfico aparece próximo do trecho de texto que ele explica.

# Séries e agrupamentos

- Use múltiplos campos em `y` somente quando as séries compartilham unidade e escala comparáveis.
- Use `hue` para um agrupamento categórico adicional quando sua cardinalidade for pequena e a
  comparação continuar legível.
- Não combine múltiplos campos `y` com `hue` na mesma visualização.
- Para `scatter`, use exatamente um campo `y`.
- Use orientação horizontal apenas para barras quando isso melhorar a leitura das categorias.

# Granularidade e volume

A consulta deve produzir o mesmo grão necessário para a visualização. Cálculos de negócio,
agregações, contagens, médias e agrupamentos pertencem à investigação/SQL, não ao renderer.

Prepare conjuntos compactos: no máximo 100 linhas por visualização e no máximo 8 séries. Se o
resultado bruto for maior, agregue ou filtre antes de apresentá-lo.

# Validação antes da resposta

Antes de considerar uma visualização, confirme:

1. os valores vieram de resultados reais desta execução;
2. todos os campos que serão usados existem nos dados;
3. os campos de valores usados em gráficos são numéricos;
4. a granularidade já corresponde à visualização desejada;
5. o tipo escolhido responde melhor à pergunta do que as alternativas;
6. a visualização solicitada explicitamente pelo usuário é respeitada quando compatível com os
   dados;
7. cada visualização adicional acrescenta informação analítica distinta.

A resposta final possui um protocolo próprio para serializar essas visualizações inline. Sua
responsabilidade nesta etapa é garantir que existam evidências corretas, compactas e bem
estruturadas para esse protocolo. Nunca invente valores para completar um gráfico.
