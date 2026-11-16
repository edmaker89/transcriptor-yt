# Como contribuir

Obrigado pelo interesse. Antes de começar, leia o `SKILL.md` e o
`references/whisper.md`: eles definem o comportamento que o agente segue.

## Ambiente de desenvolvimento

```bash
git clone https://github.com/edmaker89/transcriptor-yt ~/dev/transcriptor-yt
cd ~/dev/transcriptor-yt
python3 -m py_compile scripts/*.py install.py   # confere a sintaxe
python3 scripts/transcribe_video.py --verificar  # confere o ambiente
```

Para testar a transcrição de ponta a ponta, precisa de internet, `yt-dlp` e
`ffmpeg`. Para o caminho do Whisper, precisa também de `mlx-whisper` ou
`openai-whisper`.

## Antes de abrir um pull request

- Rode `py_compile` nos scripts.
- Se mudou o pipeline, teste com um vídeo que tenha legenda automática e outro
  sem legenda, forçando `--fonte whisper`.
- Se mudou o modelo do `mlx_whisper`, atualize o commit e o hash em
  `MODELOS_MLX` e em `references/whisper.md`, e diga na descrição do PR como
  verificou o hash.

## Regras do projeto

- **Scripts sem dependências além da biblioteca padrão**, exceto
  `huggingface_hub`, que vem junto com o `mlx-whisper`.
- **Nada é instalado sem autorização.** O código não instala Whisper nem baixa
  modelo por conta própria, a não ser no comando `--preparar` ou na transcrição
  com `--fonte whisper`, que o agente só dispara depois do aval do usuário.
- **Modelos só com commit e hash fixados** no caminho do `mlx_whisper`.
- **A nota não tem tradução, glossário, diagrama nem explicação.** Essas partes
  ficam fora de escopo, para outra skill.
- Mensagens de commit no imperativo, em português.

## Reportar problemas

Abra uma issue com: a URL do vídeo (ou um vídeo parecido), o comando usado, a
saída completa do script e o `--verificar`.
