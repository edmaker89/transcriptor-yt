#!/usr/bin/env python3
"""Instala a skill transcriptor-yt no diretório de skills do agente.

Uso:
    python3 install.py [--destino DIR]

Padrão de destino: ~/.config/opencode/skills. Em Mac e Linux cria um link
simbólico, para que atualizações com `git pull` valham na hora. No Windows,
sem permissão para link, copia a pasta.

Não instala o Whisper. Ele só é usado quando a transcrição não tem legenda, e
a skill pede autorização antes de instalar qualquer coisa.
"""

import argparse
import os
import platform
import shutil
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = "transcriptor-yt"

DICAS = {
    "Darwin": {
        "yt-dlp": "brew install yt-dlp",
        "ffmpeg": "brew install ffmpeg",
    },
    "Windows": {
        "yt-dlp": "winget install yt-dlp.yt-dlp",
        "ffmpeg": "winget install Gyan.FFmpeg",
    },
}
DICAS_PADRAO = {
    "yt-dlp": "pip install yt-dlp (ou o gerenciador de pacotes da sua distribuição)",
    "ffmpeg": "instale pelo gerenciador de pacotes da sua distribuição",
}


def checar_base():
    faltando = []
    for ferramenta in ("yt-dlp", "ffmpeg"):
        if shutil.which(ferramenta):
            print(f"ok: {ferramenta}")
        else:
            faltando.append(ferramenta)
            dica = DICAS.get(platform.system(), {}).get(ferramenta, DICAS_PADRAO[ferramenta])
            print(f"falta: {ferramenta}  ->  {dica}")
    return faltando


def instalar_em(destino):
    os.makedirs(destino, exist_ok=True)
    alvo = os.path.join(destino, NOME)
    if os.path.lexists(alvo):
        if os.path.islink(alvo) and os.path.realpath(alvo) == os.path.realpath(RAIZ):
            print(f"já instalado: {alvo}")
            return alvo
        raise SystemExit(f"{alvo} já existe e não é este projeto. Remova-o antes de instalar.")
    try:
        os.symlink(RAIZ, alvo, target_is_directory=True)
        modo = "link"
    except OSError:
        shutil.copytree(RAIZ, alvo, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        modo = "cópia"
    print(f"instalado ({modo}): {alvo}")
    return alvo


def main():
    if sys.version_info < (3, 9):
        raise SystemExit("precisa de Python 3.9 ou mais novo.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=os.path.expanduser("~/.config/opencode/skills"))
    a = ap.parse_args()

    faltando = checar_base()
    instalar_em(a.destino)

    print()
    print("Whisper (só para vídeos sem legenda). Não é instalado agora:")
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        print("  recomendado neste Mac: pip install mlx-whisper  (ou: uv tool install mlx-whisper)")
    else:
        print("  pip install openai-whisper  (puxa o PyTorch: é grande e a transcrição é mais lenta)")
    if faltando:
        print()
        print("Antes de usar a skill, instale: " + ", ".join(faltando))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
