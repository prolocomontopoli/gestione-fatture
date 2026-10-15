from pathlib import Path
import re
from pypdf import PdfReader

# True: mostra le modifiche senza rinominare.
# False: rinomina effettivamente i PDF.
DRY_RUN = False

CARTELLA = Path(__file__).resolve().parent

# Importi come 202,89 oppure 1.234,56.
# Accetta anche il punto come separatore decimale.
PATTERN_IMPORTO = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:\.\d{3})+|\d+)[,.]\d{2}(?!\d)"
)


def estrai_importo(testo: str) -> str:
    """Cerca prima un'etichetta 'Importo', poi 'Totale documento'."""

    # Esclude la tabella dei pagamenti: lì c'è un'altra intestazione
    # "Importo", che non deve prevalere sull'importo del documento.
    match_pagamenti = re.search(
        r"\bModalità\s+pagamento\b",
        testo,
        flags=re.IGNORECASE
    )
    testo_documento = (
        testo[:match_pagamenti.start()]
        if match_pagamenti
        else testo
    )

    # Prima scelta: l'importo associato a un'etichetta "Importo".
    # Esclude "Importo bollo".
    etichette_importo = list(
        re.finditer(
            r"\bImporto\b(?!\s+bollo)",
            testo_documento,
            flags=re.IGNORECASE
        )
    )

    # Prova dall'ultima etichetta utile, che in genere è quella più vicina
    # alla sezione dei totali.
    for etichetta in reversed(etichette_importo):
        zona_importo = testo_documento[
            etichetta.end():etichetta.end() + 300
        ]
        match_importo = PATTERN_IMPORTO.search(zona_importo)

        if match_importo:
            # Se prima dell'importo trovato compare "Arr.", evita di
            # interpretare quel valore come l'importo cercato.
            testo_prima_del_valore = zona_importo[:match_importo.start()]
            if re.search(r"\bArr\.?\b", testo_prima_del_valore, re.IGNORECASE):
                continue

            return match_importo.group(0)

    # Seconda scelta: "Totale documento".
    # Si ferma prima della sezione pagamenti e prende l'ultimo importo
    # presente dopo l'etichetta, così da preferire il totale all'Arr.
    match_totale = re.search(
        r"\bTotale\s+documento\b",
        testo_documento,
        flags=re.IGNORECASE
    )

    if match_totale:
        zona_totale = testo_documento[
            match_totale.end():match_totale.end() + 500
        ]
        importi_totale = PATTERN_IMPORTO.findall(zona_totale)

        if importi_totale:
            return importi_totale[-1]

    # Ultimo ripiego: usa l'ultimo importo trovato nel testo.
    importi = PATTERN_IMPORTO.findall(testo)
    if importi:
        return importi[-1]

    raise ValueError("importo non trovato")


def estrai_dati(pdf_path: Path) -> tuple[str, str, str]:
    reader = PdfReader(pdf_path)
    testo = "\n".join(page.extract_text() or "" for page in reader.pages)

    # La prima data nel testo è normalmente la data della fattura.
    match_data = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", testo)
    if not match_data:
        raise ValueError("data della fattura non trovata")

    giorno, mese, anno = match_data.groups()
    data = f"{anno}-{mese}-{giorno}"

    # Prende la prima Denominazione, quella del cedente/fornitore.
    match_fornitore = re.search(
        r"Denominazione:\s*(.+)",
        testo,
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

    importo = estrai_importo(testo)

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


for pdf in CARTELLA.glob("*.pdf"):
    try:
        data, fornitore, importo = estrai_dati(pdf)
        nome_base = f"{data} - {fornitore} - {importo}€.pdf"

        # Se il file ha già il nome atteso, o un suffisso numerico aggiunto
        # per una collisione, non rinominarlo di nuovo.
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
