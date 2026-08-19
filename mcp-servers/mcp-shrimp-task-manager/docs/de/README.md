[🇺🇸 English](../../README.md) | [🇩🇪 Deutsch](README.md) | [🇪🇸 Español](../es/README.md) | [🇫🇷 Français](../fr/README.md) | [🇮🇹 Italiano](../it/README.md) | [🇮🇳 हिन्दी](../hi/README.md) | [🇰🇷 한국어](../ko/README.md) | [🇧🇷 Português](../pt/README.md) | [🇷🇺 Русский](../ru/README.md) | [🇨🇳 中文](../zh/README.md)

# MCP Shrimp Task Manager

> 🦐 **Intelligente Aufgabenverwaltung für KI-gestützte Entwicklung** - Zerlegen Sie komplexe Projekte in verwaltbare Aufgaben, behalten Sie den Kontext über Sitzungen hinweg bei und beschleunigen Sie Ihren Entwicklungsworkflow.

<div align="center">
  
[![Shrimp Task Manager Demo](../yt.png)](https://www.youtube.com/watch?v=Arzu0lV09so)

**[Demo Video ansehen](https://www.youtube.com/watch?v=Arzu0lV09so)** • **[Schnellstart](#-schnellstart)** • **[Dokumentation](#-dokumentation)**

[![smithery badge](https://smithery.ai/badge/@cjo4m06/mcp-shrimp-task-manager)](https://smithery.ai/server/@cjo4m06/mcp-shrimp-task-manager)
<a href="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager"><img width="380" height="200" src="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager/badge" alt="Shrimp Task Manager MCP server" /></a>

</div>

## 🚀 Schnellstart

### Voraussetzungen
- Node.js 18+ 
- npm oder yarn
- MCP-kompatibler KI-Client (Claude Code, etc.)

### Installation

#### Claude Code installieren

**Windows 11 (mit WSL2):**
```bash
# Stellen Sie zunächst sicher, dass WSL2 installiert ist (in PowerShell als Administrator)
wsl --install

# WSL/Ubuntu-Umgebung betreten
wsl -d Ubuntu

# Claude Code global installieren
npm install -g @anthropic-ai/claude-code

# Claude Code starten
claude
```

**macOS/Linux:**
```bash
# Claude Code global installieren
npm install -g @anthropic-ai/claude-code

# Claude Code starten
claude
```

#### Shrimp Task Manager installieren

```bash
# Repository klonen
git clone https://github.com/cjo4m06/mcp-shrimp-task-manager.git
cd mcp-shrimp-task-manager

# Abhängigkeiten installieren
npm install

# Projekt bauen
npm run build
```

### Claude Code konfigurieren

Erstellen Sie eine `.mcp.json`-Datei in Ihrem Projektverzeichnis:

```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/pfad/zu/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/pfad/zu/ihren/shrimp_daten",
        "TEMPLATES_USE": "de",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Beispielkonfiguration:
```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/home/fire/claude/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/home/fire/claude/projekt/shrimp_daten",
        "TEMPLATES_USE": "de",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Starten Sie dann Claude Code mit Ihrer benutzerdefinierten MCP-Konfiguration:

```bash
claude --dangerously-skip-permissions --mcp-config .mcp.json
```

<details>
<summary><b>Andere KI-Clients</b></summary>

**Cline (VS Code Extension)**: Eine VS Code-Erweiterung für KI-gestützte Codierung. Zu VS Code settings.json unter `cline.mcpServers` hinzufügen

**Claude Desktop**: Zu `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) oder `%APPDATA%\Claude\claude_desktop_config.json` (Windows) hinzufügen
</details>

### Nutzung beginnen

1. **Projekt initialisieren**: `"init project rules"`
2. **Aufgabe planen**: `"plan task: Benutzerauthentifizierung implementieren"`
3. **Aufgaben ausführen**: `"execute task"` oder `"continuous mode"`

## 💡 Was ist Shrimp?

Shrimp Task Manager ist ein MCP (Model Context Protocol) Server, der transformiert, wie KI-Agenten Softwareentwicklung angehen. Anstatt Kontext zu verlieren oder Arbeit zu wiederholen, bietet Shrimp:

- **🧠 Persistenter Speicher**: Aufgaben und Fortschritt bleiben über Sitzungen hinweg bestehen
- **📋 Strukturierte Arbeitsabläufe**: Geführte Prozesse für Planung, Ausführung und Verifizierung
- **🔄 Intelligente Zerlegung**: Zerlegt komplexe Aufgaben automatisch in verwaltbare Teilaufgaben
- **🎯 Kontextbewahrung**: Verlieren Sie nie Ihren Platz, auch bei Token-Limits

## ✨ Kernfunktionen

### Aufgabenverwaltung
- **Intelligente Planung**: Tiefgreifende Analyse der Anforderungen vor der Implementierung
- **Aufgabenzerlegung**: Große Projekte in atomare, testbare Einheiten aufteilen
- **Abhängigkeitsverfolgung**: Automatische Verwaltung von Aufgabenbeziehungen
- **Fortschrittsüberwachung**: Echtzeit-Statusverfolgung und -aktualisierungen

### Erweiterte Funktionen
- **🔬 Forschungsmodus**: Systematische Erkundung von Technologien und Lösungen
- **🤖 Agentensystem**: Spezialisierte KI-Agenten spezifischen Aufgaben zuweisen ([Mehr erfahren](../agents.md))
- **📏 Projektregeln**: Codierungsstandards in Ihrem Projekt definieren und pflegen
- **💾 Aufgabenspeicher**: Automatische Sicherung und Wiederherstellung der Aufgabenhistorie

### Web-Interfaces

#### 🖥️ Task Viewer
Moderne React-Oberfläche für visuelles Aufgabenmanagement mit Drag-and-Drop, Echtzeit-Suche und Multi-Profil-Unterstützung.

**Schnelle Einrichtung:**
```bash
cd tools/task-viewer
npm install
npm run start:all
# Zugriff unter http://localhost:5173
```

[📖 Vollständige Task Viewer Dokumentation](../../tools/task-viewer/README.md)

<kbd><img src="../../tools/task-viewer/task-viewer-interface.png" alt="Task Viewer Interface" width="600"/></kbd>

#### 🌐 Web GUI
Optionale leichtgewichtige Web-Oberfläche für schnelle Aufgabenübersicht.

In `.env` aktivieren: `ENABLE_GUI=true`

## 📚 Dokumentation

- [📖 Vollständige Dokumentation](../README.md)
- [🛠️ Verfügbare Tools](../tools.md)
- [🤖 Agentenverwaltung](../agents.md)
- [🎨 Prompt-Anpassung](prompt-customization.md)
- [🔧 API-Referenz](../api.md)

## 🎯 Häufige Anwendungsfälle

<details>
<summary><b>Feature-Entwicklung</b></summary>

```
Agent: "plan task: Benutzerauthentifizierung mit JWT hinzufügen"
# Agent analysiert Codebase, erstellt Teilaufgaben

Agent: "execute task"
# Implementiert Authentifizierung schrittweise
```
</details>

<details>
<summary><b>Fehlerbehebung</b></summary>

```
Agent: "plan task: Memory Leak in Datenverarbeitung beheben"
# Agent erforscht Problem, erstellt Behebungsplan

Agent: "continuous mode"
# Führt alle Behebungsaufgaben automatisch aus
```
</details>

<details>
<summary><b>Forschung & Lernen</b></summary>

```
Agent: "research: React vs Vue für dieses Projekt vergleichen"
# Systematische Analyse mit Vor- und Nachteilen

Agent: "plan task: Komponente zum gewählten Framework migrieren"
# Erstellt Migrationsplan basierend auf Forschung
```
</details>

## 🛠️ Konfiguration

### Umgebungsvariablen

Erstellen Sie eine `.env`-Datei:

```bash
# Erforderlich
DATA_DIR=/pfad/zur/datenspeicherung

# Optional
ENABLE_GUI=true          # Web GUI aktivieren
WEB_PORT=3000           # Benutzerdefinierter Web-Port
PROMPT_LANGUAGE=de      # Prompt-Sprache (de, en, zh, etc.)
```

### Verfügbare Befehle

| Befehl | Beschreibung |
|---------|-------------|
| `init project rules` | Projektstandards initialisieren |
| `plan task [beschreibung]` | Aufgabenplan erstellen |
| `execute task [id]` | Spezifische Aufgabe ausführen |
| `continuous mode` | Alle Aufgaben sequenziell ausführen |
| `list tasks` | Alle Aufgaben anzeigen |
| `research [thema]` | Forschungsmodus betreten |
| `reflect task [id]` | Aufgabe überprüfen und verbessern |

## 🤝 Mitwirken

Wir begrüßen Beiträge! Siehe unseren [Leitfaden für Mitwirkende](../../CONTRIBUTING.md) für Details.

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert - siehe die [LICENSE](../../LICENSE)-Datei für Details.

## 🌟 Credits

Erstellt von [cjo4m06](https://github.com/cjo4m06) und gepflegt von der Community.

---

<p align="center">
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager">GitHub</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/issues">Issues</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/discussions">Diskussionen</a>
</p>