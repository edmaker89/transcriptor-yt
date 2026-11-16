#!/usr/bin/env python3
"""Instala a skill transcriptor-yt no diretório de skills do agente.

Uso:
    python3 install.py                      # instala a skill e confere as dependências
    python3 install.py --instalar-deps      # também instala yt-dlp e ffmpeg (pede confirmação)
    python3 install.py --instalar-deps --sim  # igual, sem perguntar (para o agente, depois do aval)
    python3 install.py --destino DIR        # outro diretório de skills

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

COMANDOS = {
    "Darwin": {
        "yt-dlp": ["brew", "install", "yt-dlp"],
        "ffmpeg": ["brew", "install", "ffmpeg"],
    },
    "Windows": {
        "yt-dlp": ["winget", "install", "--id", "yt-dlp.yt-dlp", "-e"],
        "ffmpeg": ["winget", "install", "--id", "Gyan.FFmpeg", "-e"],
    },
}
DICAS_MANUAIS = {
    "yt-dlp": "use o gerenciador de pacotes da sua distribuição (ex.: apt, dnf, pacman)",
    "ffmpeg": "use o gerenciador de pacotes da sua distribuição (ex.: apt, dnf, pacman)",
}


def checar_base():
    faltando = []
    for ferramenta in ("yt-dlp", "ffmpeg"):
        if shutil.which(ferramenta):
            print(f"ok: {ferramenta}")
        else:
            faltando.append(ferramenta)
            print(f"falta: {ferramenta}")
    return faltando


def instalar_deps(faltando, sim):
    """Instala o que falta, pedindo confirmação. Só usa gerenciadores conhecidos."""
    sistema = platform.system()
    comandos = COMANDOS.get(sistema)
    if not comandos:
        print("instalação automática não disponível neste sistema:")
        for f in faltando:
            print(f"  {f}: {DICAS_MANUAIS[f]}")
        return False

    gerenciador = comandos[faltando[0]][0]
    if not shutil.which(gerenciador):
        print(f"{gerenciador} não está instalado. Instale-o primeiro e rode de novo.")
        return False

    for f in faltando:
        cmd = comandos[f]
        print(f"comando: {' '.join(cmd)}")
        if not sim and input(f"Instalar {f} agora? [s/N] ").strip().lower() not in ("s", "sim", "y", "yes"):
            print(f"{f}: pulado.")
            continue
        if os.system(" ".join(cmd)) != 0:
            print(f"falha ao instalar {f}. Veja a mensagem acima.")
            return False
    return True


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
    ap.add_argument("--instalar-deps", action="store_true",
                    help="instala yt-dlp e ffmpeg se faltarem (pede confirmação)")
    ap.add_argument("--sim", action="store_true",
                    help="não pergunta ao instalar as dependências (use só com aval do usuário)")
    a = ap.parse_args()

    faltando = checar_base()
    if faltando and a.instalar_deps:
        instalar_deps(faltando, a.sim)
        faltando = [f for f in faltando if not shutil.which(f)]

    instalar_em(a.destino)

    print()
    print("Whisper (só para vídeos sem legenda). Não é instalado agora:")
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        print("  recomendado neste Mac: pip install mlx-whisper  (ou: uv tool install mlx-whisper)")
    else:
        print("  pip install openai-whisper  (puxa o PyTorch: é grande e a transcrição é mais lenta)")

    if faltando:
        print()
        print("Ainda falta instalar: " + ", ".join(faltando))
        print("Rode com --instalar-deps, ou instale manualmente e confira com: "
              "python3 scripts/transcribe_video.py --verificar")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
