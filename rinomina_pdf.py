import csv
import shutil
from pathlib import Path

from pypdf import PdfWriter


BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "elenco.csv"
FATTURE_DIR = BASE_DIR / "fatture"
RICEVUTE_DIR = BASE_DIR / "ricevute"
OUTPUT_DIR = BASE_DIR / "output"
PDF_UNICO = OUTPUT_DIR / "documenti_ordinati.pdf"

COL_FATTURA = "Nome file fattura"
COL_RICEVUTA = "Nome file ricevuta 1"
COL_ESISTENZA = "PDF fattura"


def leggi_csv(percorso):
    # utf-8-sig gestisce anche i CSV salvati da Excel con BOM.
    with percorso.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="~")
        except csv.Error:
            dialect = csv.excel

        return list(csv.DictReader(file, dialect=dialect))


def percorso_file(cartella, nome):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Nel CSV è presente un nome file vuoto.")

    percorso = cartella / nome
    if not percorso.is_file():
        raise FileNotFoundError(f"File non trovato: {percorso}")
    return percorso


def main():
    if not CSV_FILE.is_file():
        raise FileNotFoundError(f"CSV non trovato: {CSV_FILE}")

    righe = leggi_csv(CSV_FILE)
    if not righe:
        raise ValueError("Il CSV non contiene righe di dati.")

    # Controlla che il CSV abbia tutte le intestazioni attese.
    colonne = set(righe[0].keys())
    colonne_richieste = {COL_FATTURA, COL_RICEVUTA, COL_ESISTENZA}
    mancanti = colonne_richieste - colonne
    if mancanti:
        raise ValueError(
            "Colonne mancanti nel CSV: " + ", ".join(sorted(mancanti))
        )

    # Prima verifica tutti i file sorgente, così da non iniziare una copia
    # se ci sono nomi o file mancanti.
    documenti = []
    for numero_riga, riga in enumerate(righe, start=2):
        stato = (riga[COL_ESISTENZA] or "").strip().upper()
        nome_fattura = (riga[COL_FATTURA] or "").strip()
        nome_ricevuta = (riga[COL_RICEVUTA] or "").strip()

        if stato == "APRI FATTURA":
            documenti.append(
                (percorso_file(FATTURE_DIR, nome_fattura), "fattura")
            )
        elif stato == "NO":
            pass
        else:
            raise ValueError(
                f"Valore non valido in '{COL_ESISTENZA}' "
                f"alla riga {numero_riga}: {stato!r}. "
                "Sono ammessi solo 'APRI FATTURA' e 'NO'."
            )

        documenti.append(
            (percorso_file(RICEVUTE_DIR, nome_ricevuta), "ricevuta")
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_creati = []
    for numero, (sorgente, tipo) in enumerate(documenti, start=1):
        destinazione = OUTPUT_DIR / f"{numero:04d}_{tipo}.pdf"
        shutil.copy2(sorgente, destinazione)
        file_creati.append(destinazione)

    writer = PdfWriter()
    try:
        for pdf in file_creati:
            writer.append(str(pdf))

        with PDF_UNICO.open("wb") as file_output:
            writer.write(file_output)
    finally:
        writer.close()

    print(f"Copiati {len(file_creati)} PDF in: {OUTPUT_DIR}")
    print(f"Creato il PDF unico: {PDF_UNICO}")


if __name__ == "__main__":
    main()