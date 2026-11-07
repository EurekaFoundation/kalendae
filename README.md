# Kalendae

**Kalendae** è un calendario libero e open source in stile Google Calendar, scritto in Python con Qt (PySide6).
Le *Kalendae* (calende) erano il primo giorno di ogni mese nel calendario romano: da qui viene la parola «calendario».

Funziona interamente in locale: i dati restano sul computer, in un database SQLite.

## Funzionalità

- Viste **Giorno**, **Settimana**, **Mese** e **Agenda** (prossimi 30 giorni)
- Più **calendari** colorati (Personale, Lavoro, Scuola…) da mostrare o nascondere
- Eventi con orario o **tutto il giorno**, anche su più giorni
- **Eventi ricorrenti**
  - ogni giorno / settimana / mese / anno, con intervallo ("ogni 2 settimane")
  - **più giorni della settimana** ("lunedì e giovedì", "dal lunedì al venerdì")
  - mensili per **posizione** ("il secondo martedì", "l'ultimo venerdì del mese")
  - fine **mai**, **a una data** o **dopo N volte**
- **Modifica di una singola occorrenza**: come in Google Calendar si sceglie *Questo evento*,
  *Questo e tutti gli eventi successivi* o *Tutti gli eventi*, sia modificando, sia trascinando, sia eliminando
- **Trascinamento** nella griglia oraria: trascina su uno spazio vuoto per creare, trascina un evento per spostarlo,
  trascina il bordo inferiore per cambiarne la durata (aggancio ai 15 minuti)
- **Tema chiaro, scuro o come il sistema** (*Visualizza → Tema*)
- **Stampa** con anteprima ed **esportazione PDF** della vista corrente (giorno, settimana, mese, agenda)
- **Promemoria** con notifica di sistema; chiudendo la finestra Kalendae resta nell'area di notifica
- **Ricerca** per titolo, luogo e descrizione
- **Import/Export .ics**, compatibile con Google Calendar, Outlook e Thunderbird
- Ricorda vista, tema e dimensioni della finestra

## Installazione (utenti)

Scarica il pacchetto per il tuo sistema dalla pagina **Releases** del repository:

| Sistema | File | Come si installa |
|---|---|---|
| Windows | `Kalendae-x.y.z-windows-setup.exe` | doppio clic; non servono diritti di amministratore |
| Windows | `Kalendae-x.y.z-windows-portable.zip` | estrai e avvia `Kalendae.exe` (es. da chiavetta USB) |
| macOS | `Kalendae-x.y.z-macos.zip` | estrai e sposta `Kalendae.app` in Applicazioni; la prima volta clic destro → **Apri** (l'app non è firmata da Apple) |
| Linux | `Kalendae-x.y.z-linux-x86_64.tar.gz` | estrai ed esegui `./install-linux.sh` (o avvia direttamente `./Kalendae`) |

Non serve installare Python.

## Avvio dai sorgenti (sviluppatori)

Serve Python 3.10 o successivo.

```bash
cd kalendae
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt
python -m kalendae
```

Per usare un database diverso (es. uno per la scuola): `python -m kalendae --db percorso/scuola.db`

## Creare i pacchetti

### Automaticamente con GitHub Actions

Il workflow `.github/workflows/build.yml` fa tutto da solo:

- a **ogni push** esegue i test e crea i pacchetti per Windows, macOS e Linux; si scaricano dalla
  scheda *Actions* → run → sezione *Artifacts*;
- quando pubblichi un **tag di versione** crea anche una **Release** con i pacchetti allegati:

```bash
git tag v0.2.0
git push origin v0.2.0
```

Ricordati di aggiornare prima `__version__` in `kalendae/__init__.py` e `version` in `pyproject.toml`.

### A mano sul tuo computer

```bash
pip install -r requirements.txt pyinstaller pillow
python scripts/build.py
```

Il risultato è in `dist/`. Su Windows, per l'installer serve [Inno Setup 6](https://jrsoftware.org/isinfo.php):
`iscc /DMyAppVersion=0.2.0 packaging\kalendae.iss`.

## Scorciatoie

| Tasto | Azione |
|---|---|
| Ctrl+N | Nuovo evento |
| D / W / M / A | Giorno / Settimana / Mese / Agenda |
| T | Vai a oggi |
| J / K | Periodo successivo / precedente |
| Ctrl+F | Cerca |
| Ctrl+P | Stampa (con anteprima) |
| Ctrl+Shift+P | Esporta in PDF |
| Ctrl+I / Ctrl+E | Importa / Esporta .ics |

## Importare da Google Calendar

In Google Calendar: *Impostazioni → Importa ed esporta → Esporta*. Si scarica uno zip con un file `.ics`
per ogni calendario; in Kalendae usa *File → Importa da file .ics…* e scegli il calendario di destinazione.
Gli eventi già importati (stesso UID) vengono saltati. Vengono importati anche gli eventi di una serie
modificati singolarmente (RECURRENCE-ID).

Regole di ricorrenza supportate: FREQ, INTERVAL, UNTIL, COUNT, EXDATE, BYDAY (più giorni nella settimanale;
"2TU", "-1FR" nella mensile) e BYSETPOS nello stile di Outlook. Regole più rare vengono semplificate.

## Dove sono i dati

| Sistema | Percorso |
|---|---|
| Windows | `%APPDATA%\Kalendae\kalendae.db` |
| macOS | `~/Library/Application Support/Kalendae/kalendae.db` |
| Linux | `~/.local/share/Kalendae/kalendae.db` |

I database della versione 0.1 vengono aggiornati automaticamente al primo avvio.

## Struttura del codice

```
kalendae/
├── __main__.py          avvio dell'applicazione
├── database.py          SQLite: calendari, eventi, occorrenze, ricerca, migrazioni
├── recurrence.py        espansione delle ricorrenze e descrizione in italiano
├── series.py            modifica/eliminazione con ambito (questo, successivi, tutti)
├── ics.py               import/export iCalendar
├── reminders.py         servizio promemoria
├── utils.py             nomi italiani, formattazione, icone
└── ui/
    ├── main_window.py   finestra principale, menu, barra superiore
    ├── sidebar.py       pulsante Crea, mini calendario, elenco calendari
    ├── week_view.py     vista Giorno/Settimana con trascinamento
    ├── month_view.py    vista Mese
    ├── agenda_view.py   vista Agenda e risultati di ricerca
    ├── event_dialog.py  finestra evento e scelta dell'ambito
    ├── theme.py         tema chiaro/scuro
    └── printing.py      stampa ed esportazione PDF
packaging/               installer Windows, file .desktop e installazione Linux
scripts/build.py         build con PyInstaller
tests/                   test (pytest)
```

## Test

```bash
pip install pytest
python -m pytest tests
```

## Idee per le prossime versioni

- Sincronizzazione CalDAV (Nextcloud, Radicale, Google)
- Orario scolastico importabile da foglio di calcolo
- Trascinamento degli eventi anche nella vista Mese

## Licenza

MIT — vedi il file `LICENSE`.
