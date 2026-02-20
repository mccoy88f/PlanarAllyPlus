<p align="center"><a href="https://planarally.io" target="_blank" rel="noopener noreferrer"><img width="200" src="https://www.planarally.io/logos/pa-logo-background.svg" alt="PlanarAlly Plus logo"></a></p>

<p align="center"><small>Read in: <a href="README.it.md">Italian</a></small></p>

<p align="center">
    <a href="https://github.com/mccoy88f/PlanarAllyPlus/releases"><img src="https://img.shields.io/github/downloads/mccoy88f/PlanarAllyPlus/total.svg" alt="Downloads"></a>
    <a href="https://github.com/mccoy88f/PlanarAllyPlus/releases/latest"><img alt="GitHub release (latest by date)" src="https://img.shields.io/github/v/release/mccoy88f/PlanarAllyPlus"></a>
    <a href="https://discord.gg/mubGnTe" title="Join the discord server!"><img src="https://img.shields.io/discord/695640902135185449?logo=discord" alt="Discord invite button" /></a>
    <a href="https://planarally.io" title="Visit the planarally documentation"><img src="https://img.shields.io/badge/docs-read-lightblue.svg" alt="Documentation site button" /></a>
    <a href="https://patreon.com/planarally" title="Donate to this project using Patreon"><img src="https://img.shields.io/badge/patreon-donate-red.svg" alt="Patreon donate button" /></a>
</p>

# PlanarAlly Plus

A fork of version 2026.1 with extensions and improved features.

A companion tool for when you travel into the planes. PlanarAlly Plus is a web tool that adds virtual battlemaps with various extras to your TTRPG/D&D toolbox.

## What’s new in PlanarAlly Plus

This fork adds these extensions and features:

- **Documents** — Upload and view PDF documents. Share documents with players.
- **AI Generator** — Connect to AI models (OpenRouter, Google AI Studio) for characters, stories, maps, and more.
- **DungeonGen** — Procedural dungeon generation for tabletop maps.
- **Compendium** — Install multiple knowledge bases (JSON), search in character sheets and elsewhere.
- **Character Sheet** — D&D 5e character sheets for tokens (view/edit; DM sees all, players see their own).
- **Assets Installer** — Upload ZIP files to install asset packs into the assets folder.
- **Time Manager** — Timer and countdown with audio alert; runs in the background when the modal is closed.
- **Guide** — Integrated documentation and user guide (IT/EN).
- **Ambient Music** — Playlists and ambient audio from assets.

## Core features

**Self hosting**: You can run this software wherever you like without having to rely on an external service\
**Offline support**: This tool can be used in a completely offline set-up for when you play D&D in a dark dungeon.

**Simple layers**: Organize your scenes in layers for easier management.\
**Infinite canvas**: When a limited workspace is still not enough!\
**Dynamic lighting**: Increase your immersion by working with light and shadows.\
**Player vision**: Limit vision to what your token(s) can see. Is your companion in a different room, no light for you!\
**Initiative tracker**: Simple initiative tracker\
**Floors!**: Look down upon lower floors when standing on a balcony!

This tool is provided free to use and is open source.

# Downloads

_Typically only one person in your group should have to download and install PA, alternatively you can use [a publicly hosted version](https://www.planarally.io/server/setup/managed/)._

Releases of PlanarAlly Plus can be found on [the release page](https://github.com/mccoy88f/PlanarAllyPlus/releases).

For more information on how to use/install PA, see the documentation.

# Quick start from source

Scripts in the `scripts/` folder verify prerequisites, install dependencies, and start the PlanarAlly Plus server:

- **Linux/macOS**: `./scripts/run.sh`
- **Windows** (PowerShell): `.\scripts\run.ps1`
- **Windows** (Command Prompt): `scripts\run.bat`

Prerequisites: Node.js 20+, Python 3.13+, [uv](https://docs.astral.sh/uv/getting-started/installation/).

# Launcher app (download + run)

The launcher in `launcher/` is a desktop app that **downloads** the repo ZIP, extracts it and starts the server. You don't need to rebuild it when the code changes; the executable stays valid.

- **Start**: downloads (if needed), extracts, starts server
- **Update**: re-downloads the ZIP and re-extracts
- **Stop/Restart**: server control

See [launcher/README.md](launcher/README.md) for ZIP URL configuration (fork, branch) and build instructions.

# Documentation

User documentation can be found [here](https://planarally.io/docs/).

If you wish to contribute to the docs, they are hosted in a different [repository](https://github.com/Kruptein/planarally-docs).

# Contributing

If you want to contribute to this project, you can do so in a couple of ways.

If you simply have feedback, or found a bug, go to the issues tab above. First see if your feedback/bug/issue already exists and if not create a new issue!

If you want to contribute to the actual codebase, you can read more about how to setup a development environment in the CONTRIBUTING document.

If you want to contribute some gold pieces, feel free to checkout my [Patreon](https://patreon.com/planarally)

![Example view of a player with a light source](https://github.com/Kruptein/PlanarAlly/blob/dev/extra/player_light_example.png?raw=true)
_Credits to Gogots for the background map used [source](https://gogots.deviantart.com/art/City-of-Moarkaliff-702295905)_
