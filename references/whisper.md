# Whisper

A transcrição local só entra quando o vídeo não tem legenda manual nem
automática na língua falada. O agente pede autorização antes (ver SKILL.md,
passo 2).

## Ferramentas

| Ferramenta | Quando usar | Instalação | Modelo |
|---|---|---|---|
| `mlx_whisper` | Mac com Apple Silicon. Recomendada | `pip install mlx-whisper` ou `uv tool install mlx-whisper` | `large-v3-turbo` com commit e hash fixados |
| `openai-whisper` | Windows, Linux, ou Mac sem Apple Silicon | `pip install openai-whisper` (puxa o PyTorch) | nomes oficiais (`large-v3-turbo`, `small` etc.) |

O script escolhe `mlx_whisper` quando ele está no PATH. Use `--ferramenta` para
forçar uma das duas.

## Modelo e integridade (mlx_whisper)

O modelo padrão é `mlx-community/whisper-large-v3-turbo`, com:

- commit `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb`
- SHA-256 de `weights.safetensors`: `951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6`

O script baixa esse commit exato e confere o hash. Se não bater, para e não usa
o arquivo. Os valores ficam em `MODELOS_MLX` dentro de `scripts/transcribe_video.py`.

O repositório é mantido pela comunidade (`mlx-community`), não pela Apple nem
pela OpenAI. Os pesos são uma conversão do modelo original da OpenAI. Fixar o
commit e o hash garante que o arquivo não muda sem aviso, mas não prova que a
conversão está correta.

## Modelo (openai-whisper)

Os pesos vêm dos servidores da OpenAI, e o próprio pacote confere o SHA-256.
Não há commit a fixar. O script só acompanha o progresso pelo tamanho do arquivo
no cache, com um valor aproximado.

## Progresso

Durante a transcrição, o script lê a saída da ferramenta, que traz cada trecho
como `[mm:ss.mmm --> mm:ss.mmm]`. Com isso calcula o percentual pela duração do
vídeo e grava `progresso.txt`, com marcos de 5%. O log completo fica em
`whisper.log`.

Com `mlx_whisper`, o download do modelo também grava progresso (marcos de 10%)
e confere o hash no fim.

## Limites conhecidos

- O Whisper pode produzir menos texto que a legenda automática. Num teste com
  `small`, o texto ficou cerca de 14% menor.
- Nomes próprios e termos técnicos em inglês são onde ele mais erra. Sinalize
  isso nos pontos de atenção da nota.
- O tempo de execução cresce com a duração do vídeo.
