[🇺🇸 English](../../README.md) | [🇩🇪 Deutsch](../de/README.md) | [🇪🇸 Español](README.md) | [🇫🇷 Français](../fr/README.md) | [🇮🇹 Italiano](../it/README.md) | [🇮🇳 हिन्दी](../hi/README.md) | [🇰🇷 한국어](../ko/README.md) | [🇧🇷 Português](../pt/README.md) | [🇷🇺 Русский](../ru/README.md) | [🇨🇳 中文](../zh/README.md)

# MCP Shrimp Task Manager

> 🦐 **Gestión inteligente de tareas para desarrollo impulsado por IA** - Divida proyectos complejos en tareas manejables, mantenga el contexto entre sesiones y acelere su flujo de trabajo de desarrollo.

<div align="center">
  
[![Shrimp Task Manager Demo](../yt.png)](https://www.youtube.com/watch?v=Arzu0lV09so)

**[Ver video de demostración](https://www.youtube.com/watch?v=Arzu0lV09so)** • **[Inicio rápido](#-inicio-rápido)** • **[Documentación](#-documentación)**

[![smithery badge](https://smithery.ai/badge/@cjo4m06/mcp-shrimp-task-manager)](https://smithery.ai/server/@cjo4m06/mcp-shrimp-task-manager)
<a href="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager"><img width="380" height="200" src="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager/badge" alt="Shrimp Task Manager MCP server" /></a>

</div>

## 🚀 Inicio rápido

### Prerrequisitos
- Node.js 18+ 
- npm o yarn
- Cliente IA compatible con MCP (Claude Code, etc.)

### Instalación

#### Instalar Claude Code

**Windows 11 (con WSL2):**
```bash
# Primero, asegúrese de que WSL2 esté instalado (en PowerShell como administrador)
wsl --install

# Entrar al entorno Ubuntu/WSL
wsl -d Ubuntu

# Instalar Claude Code globalmente
npm install -g @anthropic-ai/claude-code

# Iniciar Claude Code
claude
```

**macOS/Linux:**
```bash
# Instalar Claude Code globalmente
npm install -g @anthropic-ai/claude-code

# Iniciar Claude Code
claude
```

#### Instalar Shrimp Task Manager

```bash
# Clonar el repositorio
git clone https://github.com/cjo4m06/mcp-shrimp-task-manager.git
cd mcp-shrimp-task-manager

# Instalar dependencias
npm install

# Construir el proyecto
npm run build
```

### Configurar Claude Code

Cree un archivo `.mcp.json` en su directorio de proyecto:

```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/ruta/a/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/ruta/a/sus/datos_shrimp",
        "TEMPLATES_USE": "es",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Ejemplo de configuración:
```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/home/fire/claude/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/home/fire/claude/proyecto/datos_shrimp",
        "TEMPLATES_USE": "es",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Luego inicie Claude Code con su configuración MCP personalizada:

```bash
claude --dangerously-skip-permissions --mcp-config .mcp.json
```

<details>
<summary><b>Otros clientes IA</b></summary>

**Cline (Extensión VS Code)**: Una extensión de VS Code para codificación asistida por IA. Agregar a VS Code settings.json bajo `cline.mcpServers`

**Claude Desktop**: Agregar a `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) o `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
</details>

### Comenzar a usar

1. **Inicializar su proyecto**: `"init project rules"`
2. **Planificar una tarea**: `"plan task: implementar autenticación de usuario"`
3. **Ejecutar tareas**: `"execute task"` o `"continuous mode"`

## 💡 ¿Qué es Shrimp?

Shrimp Task Manager es un servidor MCP (Model Context Protocol) que transforma cómo los agentes de IA abordan el desarrollo de software. En lugar de perder contexto o repetir trabajo, Shrimp proporciona:

- **🧠 Memoria persistente**: Las tareas y el progreso persisten entre sesiones
- **📋 Flujos de trabajo estructurados**: Procesos guiados para planificación, ejecución y verificación
- **🔄 Descomposición inteligente**: Divide automáticamente tareas complejas en subtareas manejables
- **🎯 Preservación del contexto**: Nunca pierdas tu lugar, incluso con límites de tokens

## ✨ Características principales

### Gestión de tareas
- **Planificación inteligente**: Análisis profundo de requisitos antes de la implementación
- **Descomposición de tareas**: Divide proyectos grandes en unidades atómicas y comprobables
- **Seguimiento de dependencias**: Gestión automática de relaciones entre tareas
- **Monitoreo de progreso**: Seguimiento y actualizaciones de estado en tiempo real

### Capacidades avanzadas
- **🔬 Modo de investigación**: Exploración sistemática de tecnologías y soluciones
- **🤖 Sistema de agentes**: Asignar agentes de IA especializados a tareas específicas ([Más información](../agents.md))
- **📏 Reglas del proyecto**: Definir y mantener estándares de codificación en su proyecto
- **💾 Memoria de tareas**: Respaldo y restauración automática del historial de tareas

### Interfaces web

#### 🖥️ Visor de tareas
Interfaz React moderna para gestión visual de tareas con arrastrar y soltar, búsqueda en tiempo real y soporte multi-perfil.

**Configuración rápida:**
```bash
cd tools/task-viewer
npm install
npm run start:all
# Acceso en http://localhost:5173
```

[📖 Documentación completa del visor de tareas](../../tools/task-viewer/README.md)

<kbd><img src="../../tools/task-viewer/task-viewer-interface.png" alt="Interfaz del visor de tareas" width="600"/></kbd>

#### 🌐 GUI web
Interfaz web liviana opcional para vista rápida de tareas.

Habilitar en `.env`: `ENABLE_GUI=true`

## 📚 Documentación

- [📖 Documentación completa](../README.md)
- [🛠️ Herramientas disponibles](../tools.md)
- [🤖 Gestión de agentes](../agents.md)
- [🎨 Personalización de prompts](prompt-customization.md)
- [🔧 Referencia API](../api.md)

## 🎯 Casos de uso comunes

<details>
<summary><b>Desarrollo de características</b></summary>

```
Agente: "plan task: agregar autenticación de usuario con JWT"
# El agente analiza la base de código, crea subtareas

Agente: "execute task"
# Implementa la autenticación paso a paso
```
</details>

<details>
<summary><b>Corrección de errores</b></summary>

```
Agente: "plan task: corregir pérdida de memoria en procesamiento de datos"
# El agente investiga el problema, crea plan de corrección

Agente: "continuous mode"
# Ejecuta todas las tareas de corrección automáticamente
```
</details>

<details>
<summary><b>Investigación y aprendizaje</b></summary>

```
Agente: "research: comparar React vs Vue para este proyecto"
# Análisis sistemático con pros y contras

Agente: "plan task: migrar componente al framework elegido"
# Crea plan de migración basado en investigación
```
</details>

## 🛠️ Configuración

### Variables de entorno

Cree un archivo `.env`:

```bash
# Requerido
DATA_DIR=/ruta/a/almacenamiento/datos

# Opcional
ENABLE_GUI=true          # Habilitar GUI web
WEB_PORT=3000           # Puerto web personalizado
PROMPT_LANGUAGE=es      # Idioma de prompts (es, en, zh, etc.)
```

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `init project rules` | Inicializar estándares del proyecto |
| `plan task [descripción]` | Crear un plan de tarea |
| `execute task [id]` | Ejecutar tarea específica |
| `continuous mode` | Ejecutar todas las tareas secuencialmente |
| `list tasks` | Mostrar todas las tareas |
| `research [tema]` | Entrar en modo investigación |
| `reflect task [id]` | Revisar y mejorar tarea |

## 🤝 Contribuir

¡Damos la bienvenida a las contribuciones! Por favor consulte nuestra [Guía de contribución](../../CONTRIBUTING.md) para más detalles.

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - vea el archivo [LICENSE](../../LICENSE) para más detalles.

## 🌟 Créditos

Creado por [cjo4m06](https://github.com/cjo4m06) y mantenido por la comunidad.

---

<p align="center">
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager">GitHub</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/issues">Issues</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/discussions">Discusiones</a>
</p>