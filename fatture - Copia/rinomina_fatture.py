from pathlib import Path
import csv
import re
from pypdf import PdfReader

# True: mostra le modifiche senza rinominare.
# False: rinomina effettivamente i PDF.
DRY_RUN = False

CARTELLA = Path(__file__).resolve().parent
CATALOGO = CARTELLA / "catalogo_pdf.csv"

# Importi come 202,89 oppure 1.234,56.
# Accetta anche il punto come separatore decimale.
PATTERN_IMPORTO = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:\.\d{3})+|\d+)[,.]\d{2}(?!\d)"
)


def estrai_importo_ultima_pagina(testo: str) -> str:
    """Restituisce l'ultimo importo con due decimali trovato nel testo."""
    importi = PATTERN_IMPORTO.findall(testo)

    if not importi:
        raise ValueError("importo non trovato nell'ultima pagina")

    return importi[-1]


def estrai_dati(pdf_path: Path) -> tuple[str, str, str]:
    reader = PdfReader(pdf_path)

    if not reader.pages:
        raise ValueError("PDF senza pagine")

    # Cerca l'importo soltanto nell'ultima pagina.
    testo_ultima_pagina = reader.pages[-1].extract_text() or ""
    importo = estrai_importo_ultima_pagina(testo_ultima_pagina)

    # Cerca la data e il fornitore nel testo del documento.
    testo = "\n".join(page.extract_text() or "" for page in reader.pages)

    # La prima data nel testo è normalmente la data della fattura.
    match_data = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", testo)
    if not match_data:
        raise ValueError("data della fattura non trovata")

    giorno, mese, anno = match_data.groups()
    data = f"{anno}-{mese}-{giorno}"

    # Limita la ricerca al riquadro del fornitore,
    # prima di quello del cliente.
    testo_fornitore = re.split(
        r"Cessionario/committente\s*\(cliente\)",
        testo,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    # Cerca "Denominazione" nel riquadro del fornitore.
    match_fornitore = re.search(
        r"\bDenominazione\s*:\s*(.+)",
        testo_fornitore,
        flags=re.IGNORECASE
    )

    # Se il fornitore è una persona fisica, usa "Cognome nome".
    if not match_fornitore:
        match_fornitore = re.search(
            r"\bCognome\s+nome\s*:\s*(.+)",
            testo_fornitore,
            flags=re.IGNORECASE
        )

    if not match_fornitore:
        raise ValueError("fornitore non trovato")

    fornitore = match_fornitore.group(1).strip()

    # Rimuove i caratteri non ammessi nei nomi dei file.
    fornitore = re.sub(r'[<>:"/\\|?*]', "-", fornitore)
    fornitore = fornitore.strip().rstrip(".")

    if not fornitore:
        raise ValueError("nome del fornitore vuoto")

    return data, fornitore, importo


def nome_disponibile(percorso: Path) -> Path:
    """Evita di sovrascrivere un file diverso già esistente."""
    if not percorso.exists():
        return percorso

    numero = 1
    while True:
        candidato = percorso.with_name(
            f"{percorso.stem} ({numero}){percorso.suffix}"
        )
        if not candidato.exists():
            return candidato
        numero += 1


def pdf_nella_cartella() -> list[Path]:
    """Restituisce i PDF direttamente contenuti nella cartella."""
    return sorted(
        (
            percorso for percorso in CARTELLA.iterdir()
            if percorso.is_file() and percorso.suffix.lower() == ".pdf"
        ),
        key=lambda percorso: percorso.name.lower(),
    )


def aggiorna_catalogo() -> None:
    """Aggiunge al CSV i nomi dei PDF non ancora registrati."""
    nomi_esistenti = set()

    if CATALOGO.exists() and CATALOGO.stat().st_size > 0:
        with CATALOGO.open("r", newline="", encoding="utf-8-sig") as file_csv:
            lettore = csv.reader(file_csv)

            for riga in lettore:
                if riga and riga[0] != "nome_file":
                    nomi_esistenti.add(riga[0])

    nomi_pdf = sorted(pdf.name for pdf in pdf_nella_cartella())
    nuovi_nomi = [nome for nome in nomi_pdf if nome not in nomi_esistenti]

    catalogo_esistente = CATALOGO.exists() and CATALOGO.stat().st_size > 0
    modalita = "a" if catalogo_esistente else "w"
    codifica = "utf-8" if catalogo_esistente else "utf-8-sig"

    with CATALOGO.open(modalita, newline="", encoding=codifica) as file_csv:
        scrittore = csv.writer(file_csv)

        if not catalogo_esistente:
            scrittore.writerow(["nome_file"])

        for nome in nuovi_nomi:
            scrittore.writerow([nome])

    print(
        f"Catalogo aggiornato: {len(nuovi_nomi)} nuovi nomi aggiunti "
        f"({CATALOGO.name})."
    )


for pdf in pdf_nella_cartella():
    try:
        data, fornitore, importo = estrai_dati(pdf)
        nome_base = f"{data} ~ {fornitore} ~ {importo}€.pdf"

        # Evita di rinominare di nuovo file già elaborati,
        # compresi quelli con un suffisso come "(1)".
        nome_gia_processato = re.fullmatch(
            re.escape(nome_base.removesuffix(".pdf"))
            + r"(?: \(\d+\))?\.pdf",
            pdf.name,
            flags=re.IGNORECASE
        )

        if nome_gia_processato:
            print(f"Già rinominato: {pdf.name}")
            continue

        destinazione = nome_disponibile(pdf.with_name(nome_base))

        if DRY_RUN:
            print(f"[ANTEPRIMA] {pdf.name} → {destinazione.name}")
        else:
            pdf.rename(destinazione)
            print(f"Rinominato: {pdf.name} → {destinazione.name}")

    except Exception as errore:
        print(f"Saltato {pdf.name}: {errore}")


try:
    aggiorna_catalogo()
except Exception as errore:
    print(f"Errore durante l'aggiornamento del catalogo: {errore}")
