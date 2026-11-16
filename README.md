# transcriptor-yt

[![Licença MIT](https://img.shields.io/github/license/edmaker89/transcriptor-yt)](LICENSE) ![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white) ![Plataformas](https://img.shields.io/badge/plataforma-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey) [![Último commit](https://img.shields.io/github/last-commit/edmaker89/transcriptor-yt)](https://github.com/edmaker89/transcriptor-yt/commits/main) [![Estrelas](https://img.shields.io/github/stars/edmaker89/transcriptor-yt?style=social)](https://github.com/edmaker89/transcriptor-yt)

Skill para agentes de código (OpenCode, Claude Code e similares) que transcreve um
vídeo do YouTube e organiza o resultado numa nota em markdown.

A nota traz:

- metadados do vídeo (canal, data, duração, visualizações);
- classificação em propósito e formato (preenchida pelo agente);
- resumo, pontos importantes e pontos de atenção (preenchidos pelo agente);
- descrição original e links;
- transcrição organizada por capítulo oficial, ou por bloco de tempo quando o
  vídeo não tem capítulos.

A transcrição não é traduzida. Ela sai no idioma falado no vídeo.

## Como funciona a fonte do texto

1. **Legenda manual** do autor, se existir na língua falada.
2. **Legenda automática** do YouTube, se não houver manual.
3. **Whisper** (local), só se as anteriores não existirem, e só com autorização
   do usuário. Em Mac com Apple Silicon, usa `mlx_whisper`. Nos demais sistemas,
   `openai-whisper`.

## Requisitos

- Python 3.9 ou mais novo
- `yt-dlp` e `ffmpeg` no PATH
- Para o Whisper (só quando necessário): `mlx-whisper` ou `openai-whisper`

Instalação das dependências básicas:

| Sistema | Comando |
|---|---|
| macOS | `brew install yt-dlp ffmpeg` |
| Windows | `winget install yt-dlp.yt-dlp` e `winget install Gyan.FFmpeg` |
| Linux | use o gerenciador de pacotes da sua distribuição |

## Instalação

### Pelo agente (o mais fácil)

Cole este prompt no seu agente (OpenCode, Claude Code ou outro):

```text
Instale a skill transcriptor-yt a partir de https://github.com/edmaker89/transcriptor-yt.
1. Clone o repositório em ~/dev/transcriptor-yt.
2. Rode: python3 install.py (se você não for o OpenCode, use --destino com a pasta de skills do seu agente)
3. Se o install.py avisar que yt-dlp ou ffmpeg faltam, me pergunte antes de
   instalar. Só depois da minha confirmação, rode: python3 install.py --instalar-deps --sim
4. Rode: python3 scripts/transcribe_video.py --verificar e me mostre o resultado.
Não instale o Whisper agora: ele só é instalado se eu pedir, quando um vídeo não tiver legenda.
```

### Manualmente

```bash
git clone https://github.com/edmaker89/transcriptor-yt ~/dev/transcriptor-yt
cd ~/dev/transcriptor-yt
python3 install.py
```

Se faltarem `yt-dlp` ou `ffmpeg`, o `install.py` diz quais. Para instalar com
confirmação:

```bash
python3 install.py --instalar-deps
```

No Mac, isso usa o Homebrew. No Windows, usa o winget. No Linux, use o gerenciador
da sua distribuição.

Por padrão, o `install.py` cria um link em `~/.config/opencode/skills/`. Para
outro agente, passe o destino:

```bash
python3 install.py --destino ~/.claude/skills
```

No Windows, sem permissão para criar links, o instalador copia a pasta. Depois
de atualizar o repositório, rode `install.py` de novo.

Para conferir o ambiente sem baixar nada:

```bash
python3 scripts/transcribe_video.py --verificar
```

## Uso pelo agente

Peça ao agente algo como "transcreve esse vídeo: <url>". O agente segue o
`SKILL.md`: verifica o ambiente, tenta a legenda, pede autorização se precisar
do Whisper, roda a transcrição em segundo plano e preenche a nota.

## Uso direto pelo terminal

```bash
python3 scripts/transcribe_video.py "https://youtu.be/XXXX" --out-dir ./saida
```

Opções úteis:

| Opção | Para quê |
|---|---|
| `--fonte auto` | legenda manual, depois automática (padrão) |
| `--fonte whisper` | transcreve o áudio localmente |
| `--ferramenta mlx` ou `openai` | escolhe a ferramenta do Whisper |
| `--whisper-model` | modelo do Whisper (padrão `large-v3-turbo`) |
| `--preparar` | só baixa e verifica o modelo do mlx_whisper |
| `--verificar` | mostra o que está instalado, sem baixar nada |

Códigos de saída: `0` nota gerada, `2` erro de ambiente ou de uso, `3` sem
legenda e Whisper necessário.

## Estrutura

```text
transcriptor-yt/
├── SKILL.md              # instruções para o agente
├── install.py            # instalador
├── scripts/
│   ├── transcribe_video.py   # pipeline completo
│   └── srt_dedup.py          # dedup de janelas deslizantes em SRT
└── references/
    └── whisper.md        # ferramentas, modelo, hash e limites do Whisper
```

## Limitações

- Legendas automáticas erram nomes próprios, termos técnicos e fala rápida.
- O Whisper pode produzir menos texto que a legenda automática.
- Modelos grandes são lentos em CPU. O Whisper no Mac usa a GPU.
- O modelo padrão do `mlx_whisper` é mantido pela comunidade. O commit e o hash
  estão fixados no código, mas a conversão não foi auditada pela Apple nem pela
  OpenAI. Veja `references/whisper.md`.

## Contribuir

Veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

MIT. Veja [LICENSE](LICENSE).
