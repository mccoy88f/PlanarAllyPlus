<p align="center"><a href="https://planarally.io" target="_blank" rel="noopener noreferrer"><img width="200" src="https://www.planarally.io/logos/pa-logo-background.svg" alt="PlanarAlly Plus logo"></a></p>

<p align="center">
    <a href="https://github.com/mccoy88f/PlanarAllyPlus/releases"><img src="https://img.shields.io/github/downloads/mccoy88f/PlanarAllyPlus/total.svg" alt="Download"></a>
    <a href="https://github.com/mccoy88f/PlanarAllyPlus/releases/latest"><img alt="GitHub release (latest by date)" src="https://img.shields.io/github/v/release/mccoy88f/PlanarAllyPlus"></a>
    <a href="https://discord.gg/mubGnTe" title="Unisciti al server Discord!"><img src="https://img.shields.io/discord/695640902135185449?logo=discord" alt="Invito Discord" /></a>
    <a href="https://planarally.io" title="Visita la documentazione di PlanarAlly"><img src="https://img.shields.io/badge/docs-leggi-lightblue.svg" alt="Documentazione" /></a>
    <a href="https://patreon.com/planarally" title="Dona al progetto su Patreon"><img src="https://img.shields.io/badge/patreon-dona-red.svg" alt="Dona su Patreon" /></a>
</p>

# PlanarAlly Plus

Un fork della versione 2026.1 con estensioni e funzionalità migliorate.

Uno strumento di supporto per quando viaggi attraverso i piani. PlanarAlly Plus è un'applicazione web che aggiunge mappe di battaglia virtuali con varie funzionalità extra alla tua cassetta degli attrezzi per GDR/D&D.

- **Watabou** — Importa mappe da Watabou City Generator e One Page Dungeon. Configurazione automatica di immagini e muri.
- **Documents** — Carica e visualizza documenti PDF. Condividi documenti con i giocatori.
- **AI Generator** — Connessione a modelli AI (OpenRouter, Google AI Studio) per personaggi, storie, mappe e altro.
- **DungeonGen** — Generazione procedurale di dungeon per mappe da tavolo. Supporta la generazione automatica di muri per collisioni e luci.
- **Compendium** — Installa più compendi di conoscenza (JSON), cerca nelle schede personaggio e altrove.
- **Character Sheet** — Schede personaggio D&D 5e per i token (visualizza/modifica; il Master vede tutto, i giocatori vedono le proprie).
- **Assets Installer** — Installa asset pack da file ZIP. Include un albero delle cartelle organizzato e denominazione automatica dei pacchetti.
- **Time Manager** — Timer e conto alla rovescia con avviso audio; continua anche con il modale chiuso.
- **Guida** — Documentazione e guida utente integrate (IT/EN).
- **Musica d'ambiente** — Playlist e audio d'ambiente dagli asset.

## Funzionalità Quality of Life
- **ESC Globale per Chiudere** — Chiudi qualsiasi estensione o modale attivo con la sola pressione del tasto ESC.
- **UI Standardizzata** — Look and feel coerente tra tutte le estensioni con barre di caricamento allineate in alto e layout unificato.

## Caratteristiche di base

**Hosting autonomo**: Puoi eseguire questo software dove preferisci senza dipendere da servizi esterni.\
**Supporto offline**: Lo strumento può essere usato completamente offline, ad esempio quando giochi a D&D in una buia prigione.

**Livelli semplici**: Organizza le tue scene in livelli per una gestione più facile.\
**Tela infinita**: Quando uno spazio di lavoro limitato non basta ancora!\
**Illuminazione dinamica**: Aumenta l'immersione lavorando con luce e ombre.\
**Visione del giocatore**: Limita la vista a ciò che il tuo token può vedere. Il compagno è in un'altra stanza? Nessuna luce per te!\
**Tracciatore iniziativa**: Un semplice tracciatore dell'iniziativa.\
**Piani multipli**: Guarda i piani inferiori quando sei su un balcone!

Questo strumento è gratuito e open source.

# Download

_Di solito è sufficiente che una sola persona del gruppo scarichi e installi PA; in alternativa puoi usare [una versione ospitata pubblicamente](https://www.planarally.io/server/setup/managed/)._

Le release di PlanarAlly Plus sono disponibili nella [pagina delle release](https://github.com/mccoy88f/PlanarAllyPlus/releases).

Per maggiori informazioni su come usare/installare PA, consulta la documentazione.

# Avvio rapido da sorgenti

Gli script nella cartella `scripts/` verificano prerequisiti, installano dipendenze e avviano il server PlanarAlly Plus:

- **Linux/macOS**: `./scripts/run.sh`
- **Windows** (PowerShell): `.\scripts\run.ps1`
- **Windows** (Prompt dei comandi): `scripts\run.bat`

Prerequisiti: Node.js 20+, Python 3.13+, [uv](https://docs.astral.sh/uv/getting-started/installation/).

# Launcher app (download + avvio)

Il launcher nella cartella `launcher/` è un'app desktop che **scarica** lo ZIP della repo, lo estrae e avvia il server. Non va ricompilata quando il codice cambia: l'eseguibile resta valido.

- **Avvia**: scarica (se necessario), estrae, avvia server
- **Aggiorna**: riscarica lo ZIP e riestrae
- **Ferma/Riavvia**: controllo del server

Vedi [launcher/README.it.md](launcher/README.it.md) per la configurazione dell'URL dello ZIP (fork, branch) e le istruzioni di build.

# Documentazione

La documentazione utente si trova [qui](https://planarally.io/docs/).

Se vuoi contribuire alla documentazione, essa è ospitata in un [repository separato](https://github.com/Kruptein/planarally-docs).

# Contribuire

Se vuoi contribuire al progetto, puoi farlo in diversi modi.

Per feedback o segnalazione di bug, vai alla tab Issues qui sopra. Verifica prima se il problema esiste già e, in caso contrario, crea una nuova issue!

Per contribuire al codice, puoi leggere come configurare un ambiente di sviluppo nel documento CONTRIBUTING.

Per contribuire con qualche moneta d'oro, visita il mio [Patreon](https://patreon.com/planarally).

![Esempio di vista di un giocatore con fonte luminosa](https://github.com/Kruptein/PlanarAlly/blob/dev/extra/player_light_example.png?raw=true)
_Crediti a Gogots per la mappa di sfondo [fonte](https://gogots.deviantart.com/art/City-of-Moarkaliff-702295905)_

---

**Altre lingue**: [English](README.md)
