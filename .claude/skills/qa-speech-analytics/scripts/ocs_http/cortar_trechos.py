"""Recorta os trechos de uma amostra em WAVs curtos, para auditoria auditiva.

Lê um CSV com (item, cid, offset_s) e o corpus baixado pelo extrair_audio.py,
e escreve um WAV por trecho — assim a escuta é de segundos, não de arquivos
inteiros. Só biblioteca padrão: não precisa de ffmpeg.

Uso:
  python cortar_trechos.py --csv amostra_no5.csv --corpus ~/corpus_qa --saida ~/trechos_no5

  --antes / --depois   janela em segundos ao redor do offset (padrão 1 e 8)

O corte é feito por BYTE do chunk `data`, preservando o `fmt ` original. As
gravações do OCS são A-law (formato 6), que o módulo `wave` não abre e o
`audioop` — removido no Python 3.13 — não converte mais. Fatiando em bytes o
script fica indiferente ao codec e o trecho abre no mesmo player do original.

Os nomes de saída começam pelo `item` (F01, F02… C01…) para a escuta seguir a
ordem da planilha. RODE ON-PREM: é a voz do devedor.
"""
import argparse, csv, os, struct, sys


def _chunks(b):
    """Percorre os chunks RIFF: (id, inicio_dos_dados, tamanho)."""
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("não é RIFF/WAVE")
    i = 12
    while i + 8 <= len(b):
        cid = b[i:i + 4]
        tam = struct.unpack("<I", b[i + 4:i + 8])[0]
        yield cid, i + 8, tam
        i += 8 + tam + (tam & 1)          # chunks têm padding para tamanho par


def recortar(origem, destino, ini_s, fim_s):
    b = open(origem, "rb").read()
    fmt = dados = None
    for cid, ini, tam in _chunks(b):
        if cid == b"fmt ":
            fmt = b[ini:ini + tam]
        elif cid == b"data":
            dados = (ini, tam)
    if not fmt or not dados:
        raise ValueError("WAV sem fmt/data")

    # byteRate (bytes por segundo) e blockAlign valem para qualquer codec
    byte_rate  = struct.unpack("<I", fmt[8:12])[0]
    block      = max(1, struct.unpack("<H", fmt[12:14])[0])
    d_ini, d_tam = dados

    a = max(0, int(ini_s * byte_rate)); z = min(d_tam, int(fim_s * byte_rate))
    a -= a % block; z -= z % block
    if z <= a:
        return 0.0
    trecho = b[d_ini + a: d_ini + z]

    corpo = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt \
            + b"data" + struct.pack("<I", len(trecho)) + trecho
    with open(destino, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", len(corpo)) + corpo)
    return len(trecho) / byte_rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--corpus", required=True, help="pasta do extrair_audio (contém audio/)")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--antes", type=float, default=1.0)
    ap.add_argument("--depois", type=float, default=8.0)
    a = ap.parse_args()

    pasta_audio = os.path.join(os.path.expanduser(a.corpus), "audio")
    saida = os.path.expanduser(a.saida)
    os.makedirs(saida, exist_ok=True)

    n = falta = erro = 0
    for r in csv.DictReader(open(a.csv, encoding="utf-8")):
        wav = os.path.join(pasta_audio, f"{r['cid']}.wav")
        if not os.path.exists(wav):
            falta += 1; continue
        off = float(r["offset_s"])
        alvo = os.path.join(saida, f"{r.get('item','x')}_{r['campanha']}_{r['cid']}_{off:.0f}s.wav")
        try:
            dur = recortar(wav, alvo, off - a.antes, off + a.depois)
        except Exception as ex:
            erro += 1; print(f"  [erro] {r['cid']}: {ex}"); continue
        if dur:
            n += 1
            print(f"  {r.get('item',''):<4} {r['campanha']:<7} {off:>6.1f}s  →  {os.path.basename(alvo)} ({dur:.1f}s)")
    print(f"\n[fim] {n} trechos em {saida}"
          + (f" | {falta} sem WAV no corpus" if falta else "")
          + (f" | {erro} com erro" if erro else ""))
    if n:
        print("      F* = falhas do ASR · C* = controles que transcreveram bem (mesmo nó).")


if __name__ == "__main__":
    main()
