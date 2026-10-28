/lemo-opuscar:lemo-opuscar

Faça um filme a partir do roteiro abaixo. Este é um pedido automatizado: NÃO faça perguntas e não peça storyboard. Use estas respostas para a rodada de perguntas:
- Estilo: {style}
- Idioma da narração e das legendas: {language}
- Voz: {voice_engine}, voz "{voice_id}", velocidade {voice_speed}
- Tamanho: {width}x{height} (passe --size {width}x{height} para todas as ferramentas de render)
- Duração alvo: cerca de {duration_s} segundos
- Material próprio: nenhum
- Storyboard: não

Siga o roteiro: a narração de cada cena é o texto que deve ser falado, palavra por palavra. A coluna "visual" é uma sugestão de imagem; adapte à gramática do estilo.

Entrega obrigatória nesta pasta ({workdir}):
- film.mp4 (o filme final mixado)
- film.srt (as legendas)
- ref.jpg (um quadro forte do filme, 16:9 ou do tamanho do filme, para servir de referência visual da thumbnail)

Assim que o visual do estilo estiver definido, grave ref.jpg primeiro, antes de renderizar o filme inteiro.

Roteiro (JSON):
{script_json}
