#!/usr/bin/env python3
"""
Transcrição de vídeo do YouTube -> nota markdown com esqueleto pronto.

Fontes do texto, em ordem:
  1. manual   legenda enviada pelo autor, na língua falada
  2. auto     legenda automática do YouTube (faixa <lang>-orig)
  3. whisper  transcrição local, só quando 1 e 2 não existem e o usuário autorizou

Códigos de saída:
  0  nota gerada
  2  erro de uso ou de ambiente (ferramenta ausente, hash do modelo errado etc.)
  3  sem legenda manual nem automática: é preciso perguntar ao usuário sobre o Whisper

Uso:
    python3 transcribe_video.py --verificar [--whisper-model MODELO]
    python3 transcribe_video.py "https://youtu.be/XXXX" [--out-dir DIR]
        [--fonte auto|manual|whisper] [--ferramenta mlx|openai]
        [--whisper-model MODELO] [--primary en] [--check pt] [--bloco 120]
"""

import argparse
import bisect
import datetime
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from srt_dedup import parse_srt, dedup  # noqa: E402

PENDENTE = "<!-- PENDENTE: agente preenche -->"

PROPOSITOS = ["lazer", "estudo", "trabalho", "informacao", "decisao-de-compra", "inspiracao"]
FORMATOS = [
    "aula", "tutorial", "palestra", "entrevista-podcast", "analise-opiniao",
    "vlog-pessoal", "documentario", "show-musica-humor",
]

FONTES_TEXTO = {
    "manual": "Legenda enviada pelo autor do canal",
    "auto": "Legendas automáticas do YouTube (ASR)",
    "whisper": "Transcrição local com Whisper",
}

# Modelos do mlx_whisper com commit e hash fixados. Só estes são aceitos sem
# aviso; qualquer outro repositório precisa ser pedido explicitamente.
MODELOS_MLX = {
    "large-v3-turbo": {
        "repo": "mlx-community/whisper-large-v3-turbo",
        "revision": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
        "arquivo": "weights.safetensors",
        "sha256": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
        "tamanho": 1613977612,
    },
}
MODELO_PADRAO = "large-v3-turbo"
# Tamanho aproximado para acompanhar o download do openai-whisper (sem hash fixo).
TAMANHO_OPENAI = {"large-v3-turbo": 1620000000}


class SemFonte(Exception):
    """Não há legenda manual nem automática na língua falada."""


def run(cmd):
    """Roda um comando e devolve stdout. Falha ruidosamente, sem engolir erro."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        for rotulo, saida in (("stdout", r.stdout), ("stderr", r.stderr)):
            if saida and saida.strip():
                print(f"[{rotulo}] {saida.strip()[-1500:]}", file=sys.stderr)
        raise SystemExit(f"falhou: {' '.join(cmd[:3])} ...")
    return r.stdout


def fetch_meta(url):
    info = json.loads(run(["yt-dlp", "-J", "--skip-download", "--no-playlist", url]))
    auto = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}
    return {
        "title": info.get("title") or "",
        "channel": info.get("channel") or "",
        "upload_date": info.get("upload_date") or "",
        "duration": info.get("duration") or 0,
        "duration_string": info.get("duration_string") or "",
        "view_count": info.get("view_count"),
        "language": info.get("language") or "",
        "description": info.get("description") or "",
        "webpage_url": info.get("webpage_url") or url,
        "categories": info.get("categories") or [],
        "tags": (info.get("tags") or [])[:10],
        "chapters": info.get("chapters") or [],
        "manual_langs": sorted(manual.keys()),
        "orig_langs": sorted(k for k in auto if k.endswith("-orig")),
    }


def pick_primary(meta, primary):
    """Língua falada: vem dos metadados (`language`), nunca de um padrão fixo."""
    if primary:
        return primary
    lang_video = meta["language"].split("-")[0]
    if not lang_video:
        raise SystemExit("o YouTube não informou a língua do áudio. Rode com --primary <lang>.")
    return lang_video


def pick_check(meta, primary, check):
    """Segunda faixa para conferir termos. Só existe quando há -orig dela."""
    if check == "none":
        return None
    if check:
        return check
    for c in ("pt", "en"):
        if f"{c}-orig" in meta["orig_langs"] and c != primary:
            return c
    return None


def pick_source(meta, primary, fonte):
    """Decide de onde vem o texto. Whisper só entra quando pedido explicitamente."""
    manual = [l for l in meta["manual_langs"] if l.split("-")[0] == primary]
    auto = f"{primary}-orig" in meta["orig_langs"]

    if fonte in ("auto", "manual") and manual:
        return "manual", manual[0]
    if fonte == "manual":
        raise SemFonte(f"não há legenda manual em '{primary}'. Use --fonte auto ou --fonte whisper.")
    if fonte == "auto" and auto:
        return "auto", f"{primary}-orig"
    if fonte == "auto":
        raise SemFonte(f"não há legenda manual nem automática em '{primary}'.")
    return "whisper", primary


def download_subs(url, fonte, lang_key, out_dir):
    """Baixa a legenda em SRT. Devolve o caminho do arquivo."""
    if fonte == "manual":
        flags = ["--write-subs", "--sub-langs", lang_key]
    else:
        flags = ["--write-auto-subs", "--sub-langs", lang_key]
    run([
        "yt-dlp", "--skip-download", "--no-playlist", *flags,
        "--convert-subs", "srt",
        "-o", os.path.join(out_dir, "video.%(ext)s"), url,
    ])
    achados = glob.glob(os.path.join(out_dir, f"video.*{lang_key}.srt"))
    if not achados:
        raise SystemExit(f"yt-dlp não gerou o arquivo de legenda '{lang_key}'.")
    return achados[0]


def escolher_ferramenta(pedida, modelo):
    """mlx_whisper quando disponível (recomendado no Mac); senão openai-whisper.

    Para com erro se a ferramenta pedida não estiver instalada, sem instalar nada.
    """
    tem_mlx = bool(shutil.which("mlx_whisper"))
    tem_openai = bool(shutil.which("whisper"))
    if pedida == "mlx":
        if not tem_mlx:
            raise SystemExit("mlx_whisper não está no PATH. Instale com: pip install mlx-whisper")
        ferramenta = "mlx"
    elif pedida == "openai":
        if not tem_openai:
            raise SystemExit("whisper (openai) não está no PATH. Instale com: pip install openai-whisper")
        ferramenta = "openai"
    elif tem_mlx:
        ferramenta = "mlx"
    elif tem_openai:
        ferramenta = "openai"
    else:
        raise SystemExit("nenhum Whisper instalado. Rode --verificar e siga as instruções da skill.")
    if ferramenta == "mlx" and modelo not in MODELOS_MLX:
        raise SystemExit(f"o mlx_whisper só usa modelos verificados: {', '.join(MODELOS_MLX)}.")
    return ferramenta


def escrever_progresso(out_dir, texto):
    caminho = os.path.join(out_dir, "progresso.txt")
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    os.replace(caminho + ".tmp", caminho)


class Monitor(threading.Thread):
    """Acompanha o download pelo tamanho dos arquivos em disco e grava progresso."""

    def __init__(self, caminhos, total, out_dir, rotulo):
        super().__init__(daemon=True)
        self.caminhos, self.total, self.out_dir, self.rotulo = caminhos, total, out_dir, rotulo
        self.parar = threading.Event()
        self.marco = -10

    def tamanho(self):
        return sum(os.path.getsize(c) for c in self.caminhos() if os.path.exists(c))

    def run(self):
        while not self.parar.wait(3):
            pct = min(99, int(self.tamanho() / self.total * 100))
            if pct >= self.marco + 10:
                self.marco = pct - pct % 10
                texto = f"{self.rotulo}: {self.marco}%"
                escrever_progresso(self.out_dir, texto)
                print(f"progresso: {texto}", flush=True)

    def encerrar(self):
        self.parar.set()
        self.join()


def sha256_de(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_modelo_mlx(nome, out_dir):
    """Baixa o modelo com commit fixado, verifica o hash e devolve o diretório local."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE

    spec = MODELOS_MLX[nome]
    blobs = os.path.join(HF_HUB_CACHE, "models--" + spec["repo"].replace("/", "--"), "blobs")
    monitor = Monitor(
        lambda: glob.glob(os.path.join(blobs, "*.incomplete")),
        spec["tamanho"], out_dir, "download do modelo",
    )
    escrever_progresso(out_dir, "download do modelo: iniciando")
    print("baixando o modelo (se ainda não estiver no cache)...", flush=True)
    monitor.start()
    try:
        caminho = snapshot_download(
            spec["repo"], revision=spec["revision"],
            allow_patterns=["config.json", spec["arquivo"]],
        )
    finally:
        monitor.encerrar()

    escrever_progresso(out_dir, "verificando o hash do modelo")
    if sha256_de(os.path.join(caminho, spec["arquivo"])) != spec["sha256"]:
        raise SystemExit(
            "o hash do modelo não confere com o fixado na skill. Não use este arquivo: "
            "apague o cache desse modelo e tente de novo, ou avise o mantenedor."
        )
    escrever_progresso(out_dir, "modelo pronto")
    return caminho


def transcrever_mlx(audio, primary, out_dir, modelo_dir):
    return ["mlx_whisper", audio, "--language", primary, "--output-format", "srt",
            "--output-dir", out_dir, "--output-name", "audio", "--model", modelo_dir]


def transcrever_openai(audio, primary, out_dir, nome):
    return ["whisper", audio, "--language", primary, "--model", nome,
            "--output_format", "srt", "--output_dir", out_dir]


TRECHO_WHISPER = re.compile(
    r"\[(?:(\d+):)?(\d+):(\d+(?:\.\d+)?) --> (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]"
)


def segundos(h, m, s):
    return int(h or 0) * 3600 + int(m) * 60 + float(s)


def rodar_whisper(cmd, out_dir, duracao):
    """Roda o Whisper e acompanha a saída: grava progresso.txt e imprime marcos de 5%.

    A ferramenta imprime cada trecho como `[mm:ss.mmm --> mm:ss.mmm] texto`. O
    fim do último trecho dividido pela duração do vídeo dá o percentual.
    """
    log = open(os.path.join(out_dir, "whisper.log"), "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    marco = -5
    ultimas = []
    for linha in proc.stdout:
        log.write(linha)
        ultimas = (ultimas + [linha.rstrip()])[-15:]
        m = TRECHO_WHISPER.search(linha)
        if not m or not duracao:
            continue
        fim = segundos(*m.group(4, 5, 6))
        pct = min(100, int(fim / duracao * 100))
        if pct >= marco + 5:
            marco = pct - pct % 5
            texto = f"transcrição: {marco}% — {mmss(fim)} de {mmss(duracao)}"
            escrever_progresso(out_dir, texto)
            print(f"progresso: {texto}", flush=True)
    rc = proc.wait()
    log.close()
    if rc != 0:
        raise SystemExit("Whisper falhou. Últimas linhas:\n" + "\n".join(ultimas))
    escrever_progresso(out_dir, "transcrição: 100% — concluída")


def transcribe_whisper(url, primary, out_dir, ferramenta, nome_modelo, duracao):
    """Baixa só o áudio, prepara o modelo e transcreve. Devolve (srt, descrição)."""
    run([
        "yt-dlp", "--no-playlist", "-x", "--audio-format", "wav",
        "-o", os.path.join(out_dir, "audio.%(ext)s"), url,
    ])
    audio = os.path.join(out_dir, "audio.wav")
    if not os.path.exists(audio):
        raise SystemExit("yt-dlp não gerou o áudio audio.wav.")

    if ferramenta == "mlx":
        modelo_dir = baixar_modelo_mlx(nome_modelo, out_dir)
        cmd = transcrever_mlx(audio, primary, out_dir, modelo_dir)
        descricao = f"mlx_whisper, modelo {nome_modelo} (commit {MODELOS_MLX[nome_modelo]['revision'][:7]})"
    else:
        cmd = transcrever_openai(audio, primary, out_dir, nome_modelo)
        descricao = f"openai-whisper, modelo {nome_modelo}"
        print("o openai-whisper baixa o modelo na primeira vez (cerca de 1,6 GB para large-v3-turbo); "
              "o progresso aparece no whisper.log", flush=True)

    escrever_progresso(out_dir, "transcrição: 0% — começando")
    print("transcrição começando", flush=True)
    rodar_whisper(cmd, out_dir, duracao)
    srt = os.path.join(out_dir, "audio.srt")
    if not os.path.exists(srt):
        raise SystemExit("o Whisper não gerou audio.srt.")
    return srt, descricao


def mmss(sec):
    sec = int(sec)
    h, resto = divmod(sec, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def secoes(blocks, chapters, bloco):
    """Agrupa fragmentos [(t, texto)] em seções [(rótulo, [textos])].

    Com capítulos oficiais, a seção é o capítulo. Sem eles, blocos fixos de
    `bloco` segundos, rotulados só pelo tempo: nenhum título é inventado.
    """
    if chapters:
        bordas = sorted(
            (c["start_time"], c["title"]) for c in chapters if c.get("start_time") is not None
        )
        inicios = [t for t, _ in bordas]
        grupos = [[] for _ in bordas]
        antes = []
        for t, texto in blocks:
            i = bisect.bisect_right(inicios, t) - 1
            (grupos[i] if i >= 0 else antes).append(texto)
        secoes_ = [(f"{mmss(t)} — {titulo}", g) for (t, titulo), g in zip(bordas, grupos)]
        if antes:
            secoes_.insert(0, (f"{mmss(0)} — início", antes))
        return [(r, g) for r, g in secoes_ if g]

    grupos = {}
    for t, texto in blocks:
        chave = int(t // bloco) * bloco
        grupos.setdefault(chave, []).append(texto)
    return [(mmss(k), grupos[k]) for k in sorted(grupos)]


def links(texto):
    vistos = []
    for u in re.findall(r"https?://[^\s<>\")]+", texto):
        u = u.rstrip(".,;:)]")
        if u not in vistos:
            vistos.append(u)
    return vistos


def render_nota(meta, primary, check, fonte, origem, secs, hoje):
    data = meta["upload_date"]
    publicado = f"{data[:4]}-{data[4:6]}-{data[6:8]}" if len(data) == 8 else ""
    fonte_txt = FONTES_TEXTO[fonte]
    if fonte in ("auto", "manual"):
        fonte_txt += f" (`{origem}`)"
    elif fonte == "whisper":
        fonte_txt += f" ({origem})"
    L = [
        "---",
        f"title: {json.dumps('Transcrição — ' + meta['title'], ensure_ascii=False)}",
        f"source: {json.dumps(meta['webpage_url'])}",
        f"channel: {json.dumps(meta['channel'], ensure_ascii=False)}",
        f"published: {publicado}",
        f"duration: {json.dumps(meta['duration_string'])}",
        f"language: {primary}",
        f"created: {hoje}",
        f"transcript_source: {fonte}",
        "proposito: \"\"",
        "formato: \"\"",
        f"youtube_categories: {json.dumps(meta['categories'], ensure_ascii=False)}",
        f"tags: {json.dumps(meta['tags'], ensure_ascii=False)}",
        "---",
        "",
        f"# {meta['title']}",
        "",
        "## Metadados",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Vídeo | {meta['webpage_url']} |",
        f"| Canal | {meta['channel']} |",
        f"| Publicado em | {publicado} |",
        f"| Duração | {meta['duration_string']} |",
        f"| Visualizações | {meta['view_count'] if meta['view_count'] is not None else 'n/d'} |",
        f"| Idioma falado | {primary} |",
        f"| Fonte do texto | {fonte_txt} |",
        f"| Transcrição gerada em | {hoje} |",
        "",
        "> **Fidelidade do texto.** Nomes próprios, termos técnicos, números e fala"
        " rápida são os pontos mais suscetíveis a erro."
        + (" Faixa de conferência: `" + check + "-orig`." if check and fonte == "auto" else ""),
        "",
        "## Classificação",
        "",
        f"- Propósito: {PENDENTE} — valores: {' | '.join(PROPOSITOS)}",
        f"- Formato: {PENDENTE} — valores: {' | '.join(FORMATOS)}",
        f"- Categorias do YouTube: {', '.join(meta['categories']) or 'n/d'}",
        "",
        "## Resumo",
        "",
        PENDENTE,
        "",
        "## Pontos importantes",
        "",
        PENDENTE,
        "",
        "## Pontos de atenção",
        "",
        PENDENTE,
        "",
        "## Descrição original",
        "",
    ]
    descricao = meta["description"].strip()
    if descricao:
        L += [("> " + l).rstrip() for l in descricao.splitlines()]
    else:
        L.append("_Sem descrição._")
    L += ["", "### Links da descrição", ""]
    ls = links(meta["description"])
    L += [f"- {u}" for u in ls] if ls else ["_Nenhum link._"]
    L += ["", "## Transcrição", ""]
    for rotulo, textos in secs:
        L += [f"### {rotulo}", "", " ".join(textos), ""]
    return "\n".join(L).rstrip() + "\n"


def modelo_em_cache(spec):
    """True/False se o huggingface_hub estiver instalado; None se não der para saber."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    caminho = try_to_load_from_cache(spec["repo"], spec["arquivo"], revision=spec["revision"])
    return isinstance(caminho, str) and os.path.exists(caminho)


def verificar(modelo):
    """Relata o que está instalado, sem baixar nada. Saída em JSON."""
    sistema, arq = platform.system(), platform.machine()
    spec = MODELOS_MLX.get(modelo)
    em_cache = modelo_em_cache(spec) if spec else None
    recomendado = "mlx" if sistema == "Darwin" and arq == "arm64" else "openai"
    return {
        "sistema": sistema,
        "arquitetura": arq,
        "base": {
            "yt-dlp": bool(shutil.which("yt-dlp")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
        },
        "whisper": {
            "mlx_whisper": bool(shutil.which("mlx_whisper")),
            "openai-whisper": bool(shutil.which("whisper")),
            "recomendado": recomendado,
        },
        "modelo": {
            "nome": modelo,
            "tamanho_mb": round(spec["tamanho"] / 1e6) if spec else None,
            "em_cache": em_cache,
        },
    }


def reexecutar_no_python_do_mlx():
    """O mlx_whisper costuma ficar num ambiente próprio, com o huggingface_hub junto.

    Se o Python atual não tiver o huggingface_hub, relança o script com o Python
    do ambiente do mlx_whisper, em vez de exigir outra instalação.
    """
    import importlib.util

    if importlib.util.find_spec("huggingface_hub") is not None:
        return
    binario = shutil.which("mlx_whisper")
    if not binario:
        return
    py = os.path.join(os.path.dirname(os.path.realpath(binario)), "python3")
    if os.path.exists(py) and os.path.realpath(py) != os.path.realpath(sys.executable):
        os.execv(py, [py] + sys.argv)


def main():
    reexecutar_no_python_do_mlx()
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--verificar", action="store_true",
                    help="mostra o que está instalado e sai, sem baixar nada")
    ap.add_argument("--preparar", action="store_true",
                    help="só baixa e verifica o modelo do mlx_whisper, sem transcrever")
    ap.add_argument("--out-dir", default=None,
                    help="diretório de trabalho. Padrão: diretório temporário novo")
    ap.add_argument("--fonte", default="auto", choices=["auto", "manual", "whisper"],
                    help="auto: manual, depois automática. whisper: transcreve o áudio localmente")
    ap.add_argument("--ferramenta", default=None, choices=["mlx", "openai"],
                    help="ferramenta do Whisper. Padrão: mlx no Mac, openai nos demais")
    ap.add_argument("--whisper-model", default=MODELO_PADRAO,
                    help=f"modelo do Whisper. Padrão: {MODELO_PADRAO}")
    ap.add_argument("--primary", default=None,
                    help="língua falada (ex.: pt, en). Padrão: deduz de language do vídeo")
    ap.add_argument("--check", default=None,
                    help="2ª faixa -orig para conferir termos. Padrão: pt, depois en. 'none' pula")
    ap.add_argument("--limit", type=float, default=4.5)
    ap.add_argument("--bloco", type=int, default=120,
                    help="tamanho do bloco de tempo em segundos, quando não há capítulos")
    a = ap.parse_args()

    if a.verificar:
        print(json.dumps(verificar(a.whisper_model), ensure_ascii=False, indent=2))
        return
    if a.preparar:
        if a.whisper_model not in MODELOS_MLX:
            raise SystemExit(f"--preparar só aceita modelos verificados: {', '.join(MODELOS_MLX)}.")
        out = a.out_dir or tempfile.mkdtemp(prefix="transcriptor-yt-")
        os.makedirs(out, exist_ok=True)
        caminho = baixar_modelo_mlx(a.whisper_model, out)
        print(f"modelo pronto e verificado: {caminho}", flush=True)
        return
    if not a.url:
        ap.error("informe a URL do vídeo (ou use --verificar ou --preparar)")

    if a.out_dir is None:
        a.out_dir = tempfile.mkdtemp(prefix="transcriptor-yt-")
    os.makedirs(a.out_dir, exist_ok=True)

    meta = fetch_meta(a.url)
    primary = pick_primary(meta, a.primary)
    check = pick_check(meta, primary, a.check)
    try:
        fonte, origem = pick_source(meta, primary, a.fonte)
    except SemFonte as e:
        if a.fonte == "auto":
            print(f"PRECISA_WHISPER: {e}", flush=True)
            sys.exit(3)
        raise SystemExit(str(e))

    if fonte == "whisper":
        ferramenta = escolher_ferramenta(a.ferramenta, a.whisper_model)
        srt, origem = transcribe_whisper(
            a.url, primary, a.out_dir, ferramenta, a.whisper_model, meta["duration"]
        )
        check = None
    else:
        srt = download_subs(a.url, fonte, origem, a.out_dir)

    items = parse_srt(srt)
    final, dups = dedup(items, a.limit)
    dest = os.path.join(a.out_dir, f"{primary}.dedup.txt")
    with open(dest, "w", encoding="utf-8") as f:
        for t, frag in final:
            f.write(f"{t:.3f}\t{frag}\n")
    residuo = [
        (final[i][0] - final[i - 1][0], final[i][0])
        for i in range(1, len(final))
        if final[i][1] == final[i - 1][1]
    ]

    secs = secoes(final, meta["chapters"], a.bloco)
    hoje = datetime.date.today().isoformat()
    nota = render_nota(meta, primary, check, fonte, origem, secs, hoje)
    nota_path = os.path.join(a.out_dir, "nota.md")
    with open(nota_path, "w", encoding="utf-8") as f:
        f.write(nota)
    with open(os.path.join(a.out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    escrever_progresso(a.out_dir, "nota gerada")

    print(f"\n=== {meta['title']}")
    print(f"canal={meta['channel']}  dur={meta['duration_string']}  views={meta['view_count']}")
    print(f"língua falada: {primary}  ->  fonte: {fonte} ({origem})")
    print(f"cues={len(items)} kept={len(final)} dups={dups} residuo={len(residuo)}")
    if residuo:
        print("resíduos a conferir:", [f"{g:.2f}s@{mmss(t)}" for g, t in residuo])
    print(f"capítulos oficiais: {len(meta['chapters'])}"
          + ("" if meta["chapters"] else f" (seções de {a.bloco}s, só com tempo)"))
    print(f"categorias do YouTube: {', '.join(meta['categories']) or 'n/d'}")
    print(f"\nnota: {nota_path}\nfragmentos: {dest}\nmetadata: {a.out_dir}/metadata.json")


if __name__ == "__main__":
    main()
