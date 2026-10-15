from pathlib import Path
from datetime import datetime
import re
import fitz  # PyMuPDF

CARTELLA = Path(__file__).resolve().parent
MAX_DESCRIZIONE = 90
TOLLERANZA_Y = 8


def pulisci_parola(testo):
    return re.sub(r"\W", "", testo, flags=re.UNICODE).lower()


def trova_etichetta(parole, etichetta):
    """Trova un'etichetta composta da una o più parole sulla stessa riga."""
    cercate = [pulisci_parola(p) for p in etichetta.split()]

    for parola in parole:
        if pulisci_parola(parola[4]) != cercate[0]:
            continue

        trovate = [parola]
        precedente = parola

        for termine in cercate[1:]:
            successive = [
                p for p in parole
                if pulisci_parola(p[4]) == termine
                and p[0] >= precedente[2]
                and abs(
                    ((p[1] + p[3]) / 2) -
                    ((precedente[1] + precedente[3]) / 2)
                ) <= TOLLERANZA_Y
            ]

            if not successive:
                break

            successiva = min(successive, key=lambda p: p[0])
            trovate.append(successiva)
            precedente = successiva
        else:
            return trovate

    return None


def nome_sicuro(testo):
    testo = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " ", testo)
    return re.sub(r"\s+", " ", testo).strip(" .-")


def nome_disponibile(percorso):
    """Evita di sovrascrivere file che hanno già lo stesso nome."""
    base, estensione = percorso.stem, percorso.suffix
    candidato = percorso
    numero = 2

    while candidato.exists():
        candidato = percorso.with_name(f"{base} ({numero}){estensione}")
        numero += 1

    return candidato


for pdf in CARTELLA.glob("*.pdf"):
    try:
        with fitz.open(pdf) as documento:
            pagina = documento[0]
            parole = sorted(
                pagina.get_text("words"),
                key=lambda p: ((p[1] + p[3]) / 2, p[0]),
            )
            testo_completo = pagina.get_text("text")

        etichetta_valuta = trova_etichetta(parole, "Data Valuta")
        etichetta_descrizione = trova_etichetta(parole, "Descrizione")
        etichetta_operazione = trova_etichetta(parole, "Data Operazione")

        if not etichetta_valuta:
            raise ValueError("etichetta Data Valuta non trovata")
        if not etichetta_descrizione:
            raise ValueError("etichetta Descrizione non trovata")
        if not etichetta_operazione:
            raise ValueError("etichetta Data Operazione non trovata")

        # Data Valuta: cerca la data a destra dell'etichetta.
        x_valuta = etichetta_valuta[-1][2]
        y_valuta = (etichetta_valuta[-1][1] + etichetta_valuta[-1][3]) / 2

        date_sulla_riga = [
            p for p in parole
            if p[0] >= x_valuta
            and abs(((p[1] + p[3]) / 2) - y_valuta) <= TOLLERANZA_Y
            and re.fullmatch(r"\d{2}/\d{2}/\d{4}", p[4])
        ]

        if not date_sulla_riga:
            raise ValueError("data sulla riga di Data Valuta non trovata")

        data_originale = max(date_sulla_riga, key=lambda p: p[0])[4]
        data_file = datetime.strptime(data_originale, "%d/%m/%Y").strftime("%Y-%m-%d")

        # Uscite: usa l'importo negativo del PDF e nel nome ne mostra il valore assoluto.
        importi_negativi = re.findall(
            r"-\s*[\d.]+,\d{2}",
            testo_completo,
        )

        if not importi_negativi:
            raise ValueError("importo negativo non trovato")

        importo = importi_negativi[0].replace(" ", "").lstrip("-")

        # Descrizione: raccoglie tutte le parole tra le righe delle due etichette.
        # Non vincola l'allineamento orizzontale: include anche le righe rientrate.
        y_desc = (
            etichetta_descrizione[-1][1] +
            etichetta_descrizione[-1][3]
        ) / 2
        y_op = (
            etichetta_operazione[0][1] +
            etichetta_operazione[0][3]
        ) / 2

        parole_descrizione = [
            p for p in parole
            if y_desc - TOLLERANZA_Y
            < (p[1] + p[3]) / 2
            < y_op - TOLLERANZA_Y
            and pulisci_parola(p[4]) != "descrizione"
        ]

        descrizione = " ".join(p[4] for p in parole_descrizione)
        descrizione = nome_sicuro(descrizione)

        if not descrizione:
            raise ValueError("descrizione vuota")

        if len(descrizione) > MAX_DESCRIZIONE:
            descrizione = descrizione[:MAX_DESCRIZIONE].rstrip(" .-") + "…"

        nuovo_nome = f"{data_file} - {descrizione} - {importo}€.pdf"
        destinazione = pdf.with_name(nuovo_nome)

        if destinazione == pdf:
            print(f"Già rinominato: {pdf.name}")
            continue

        destinazione = nome_disponibile(destinazione)
        pdf.rename(destinazione)
        print(f"{pdf.name} → {destinazione.name}")

    except Exception as errore:
        print(f"Saltato {pdf.name}: {errore}")
