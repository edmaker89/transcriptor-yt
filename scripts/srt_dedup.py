#!/usr/bin/env python3
"""
Dedup de SRT de legendas automáticas do YouTube.

O ASR do YouTube emite dois tipos de cue intercalados. Cada fragmento aparece
duas vezes, e o cue de duas linhas carrega o anterior completo antes do novo:

    00:00:01,590  ['Se no meio de uma conversa sobre']                       # 1 linha = texto novo
    00:00:01,600  ['Se no meio...', 'inteligência artificial...']             # 2 linhas = anterior + novo
    00:00:03,790  ['inteligência artificial, alguém menciona']                # 1 linha = repete o anterior

Ignorar isso produz texto com cada frase repetida. Este módulo resolve os dois
problemas que quebram um parser ingênuo:

  1. Blocos SRT podem ter uma linha em branco COM ESPAÇO entre o timestamp e o
     texto. Um split por regex `\\n\\s*\\n` corta o bloco no meio e separa o
     texto do seu cue. Divida por "\\n\\n" e descarte linhas vazias por strip.
  2. Os milissegundos do SRT vêm como string ("560"), não como fração. Somar
     float(ms) em vez de int(ms)/1000 desloca TODO o timeline em segundos.

Uso:
    python3 srt_dedup.py legenda.srt [--limit 4.5] [--out saida.txt]

Formato de saída: "<segundos><TAB><fragmento>", uma linha por fragmento.
"""

import argparse
import sys


def to_sec(ts):
    """'00:01:05,150' -> 65.15 ; '00:01:05.150' -> 65.15"""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, rest = int(parts[0]), int(parts[1]), parts[2]
    elif len(parts) == 2:
        h, m, rest = 0, int(parts[0]), parts[1]
    else:
        return 0.0
    rest = rest.replace(",", ".")
    if "." in rest:
        sec, ms = rest.split(".", 1)
    else:
        sec, ms = rest, "0"
    return h * 3600 + m * 60 + int(sec) + int(ms) / 1000


def parse_srt(path):
    """Retorna [(segundos, ultima_linha_do_cue)] na ordem do arquivo."""
    raw = open(path, encoding="utf-8-sig").read()
    items = []
    for bloco in raw.split("\n\n"):
        bloco = bloco.strip()
        if not bloco:
            continue
        linhas = [l.rstrip() for l in bloco.split("\n")]
        tlinha = next((l for l in linhas if "-->" in l), None)
        if tlinha is None:
            continue
        t = to_sec(tlinha.split("-->")[0])
        texto = [
            l.strip()
            for l in linhas
            if l.strip() and "-->" not in l and not l.strip().isdigit()
        ]
        if texto:
            # só a última linha: a(s) outra(s) são o que já foi entregue antes
            items.append((t, texto[-1]))
    return items


def dedup(items, limit=4.5):
    """Remove a repetição da janela deslizante.

    Descarta o cue quando o texto é idêntico ao anterior E o intervalo de
    timestamp é menor que `limit`. O intervalo típico entre o cue simples e o
    duplicado é ~2,2 s, mas falantes mais lentos passam de 3,5 s. Num vídeo de
    teste, 3,5 s deixou 25 resíduos e 4,5 s deixou 1, removendo 24 duplicatas a
    mais, todas consecutivas e idênticas. Muito acima disso, a dedup começa a apagar repetição legítima.
    """
    final, dups = [], 0
    for t, frag in items:
        if final and final[-1][1] == frag and (t - final[-1][0]) < limit:
            dups += 1
            continue
        final.append((t, frag))
    return final, dups


def gaps(final):
    """Intervalos entre fragmentos consecutivos, do maior ao menor."""
    return sorted((final[i][0] - final[i - 1][0], i) for i in range(1, len(final)))


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Dedup de SRT do YouTube.")
    ap.add_argument("srt")
    ap.add_argument("--limit", type=float, default=4.5)
    ap.add_argument("--out")
    a = ap.parse_args()

    items = parse_srt(a.srt)
    final, dups = dedup(items, a.limit)
    dest = a.out or (a.srt.rsplit(".", 1)[0] + ".dedup.txt")
    with open(dest, "w", encoding="utf-8") as f:
        for t, frag in final:
            f.write(f"{t:.3f}\t{frag}\n")
    print(f"{a.srt}: cues={len(items)} kept={len(final)} dups={dups} -> {dest}")


if __name__ == "__main__":
    sys.exit(main())