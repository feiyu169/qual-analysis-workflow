[🇺🇸 English](../../README.md) | [🇩🇪 Deutsch](../de/README.md) | [🇪🇸 Español](../es/README.md) | [🇫🇷 Français](../fr/README.md) | [🇮🇹 Italiano](../it/README.md) | [🇮🇳 हिन्दी](../hi/README.md) | [🇰🇷 한국어](../ko/README.md) | [🇧🇷 Português](README.md) | [🇷🇺 Русский](../ru/README.md) | [🇨🇳 中文](../zh/README.md)

# MCP Shrimp Task Manager

> 🦐 **Gestão inteligente de tarefas para desenvolvimento assistido por IA** - Divida projetos complexos em tarefas gerenciáveis, mantenha o contexto entre sessões e acelere seu fluxo de trabalho de desenvolvimento.

<div align="center">
  
[![Shrimp Task Manager Demo](../yt.png)](https://www.youtube.com/watch?v=Arzu0lV09so)

**[Assistir vídeo de demonstração](https://www.youtube.com/watch?v=Arzu0lV09so)** • **[Início rápido](#-início-rápido)** • **[Documentação](#-documentação)**

[![smithery badge](https://smithery.ai/badge/@cjo4m06/mcp-shrimp-task-manager)](https://smithery.ai/server/@cjo4m06/mcp-shrimp-task-manager)
<a href="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager"><img width="380" height="200" src="https://glama.ai/mcp/servers/@cjo4m06/mcp-shrimp-task-manager/badge" alt="Shrimp Task Manager MCP server" /></a>

</div>

## 🚀 Início rápido

### Pré-requisitos
- Node.js 18+ 
- npm ou yarn
- Cliente IA compatível com MCP (Claude Code, etc.)

### Instalação

#### Instalar Claude Code

**Windows 11 (com WSL2):**
```bash
# Primeiro, certifique-se de que o WSL2 está instalado (no PowerShell como administrador)
wsl --install

# Entre no ambiente Ubuntu/WSL
wsl -d Ubuntu

# Instale o Claude Code globalmente
npm install -g @anthropic-ai/claude-code

# Inicie o Claude Code
claude
```

**macOS/Linux:**
```bash
# Instale o Claude Code globalmente
npm install -g @anthropic-ai/claude-code

# Inicie o Claude Code
claude
```

#### Instalar Shrimp Task Manager

```bash
# Clone o repositório
git clone https://github.com/cjo4m06/mcp-shrimp-task-manager.git
cd mcp-shrimp-task-manager

# Instale as dependências
npm install

# Construa o projeto
npm run build
```

### Configurar Claude Code

Crie um arquivo `.mcp.json` no diretório do seu projeto:

```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/caminho/para/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/caminho/para/seus/dados_shrimp",
        "TEMPLATES_USE": "pt",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Exemplo de configuração:
```json
{
  "mcpServers": {
    "shrimp-task-manager": {
      "command": "node",
      "args": ["/home/fire/claude/mcp-shrimp-task-manager/dist/index.js"],
      "env": {
        "DATA_DIR": "/home/fire/claude/projeto/dados_shrimp",
        "TEMPLATES_USE": "pt",
        "ENABLE_GUI": "false"
      }
    }
  }
}
```

Em seguida, inicie o Claude Code com sua configuração MCP personalizada:

```bash
claude --dangerously-skip-permissions --mcp-config .mcp.json
```

<details>
<summary><b>Outros clientes IA</b></summary>

**Cline (Extensão VS Code)**: Uma extensão do VS Code para codificação assistida por IA. Adicione ao VS Code settings.json sob `cline.mcpServers`

**Claude Desktop**: Adicione a `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
</details>

### Começar a usar

1. **Inicialize seu projeto**: `"init project rules"`
2. **Planeje uma tarefa**: `"plan task: implementar autenticação de usuário"`
3. **Execute tarefas**: `"execute task"` ou `"continuous mode"`

## 💡 O que é Shrimp?

Shrimp Task Manager é um servidor MCP (Model Context Protocol) que transforma como agentes IA abordam o desenvolvimento de software. Em vez de perder contexto ou repetir trabalho, Shrimp fornece:

- **🧠 Memória persistente**: Tarefas e progresso persistem entre sessões
- **📋 Fluxos de trabalho estruturados**: Processos guiados para planejamento, execução e verificação
- **🔄 Decomposição inteligente**: Decompõe automaticamente tarefas complexas em subtarefas gerenciáveis
- **🎯 Preservação de contexto**: Nunca perca seu lugar, mesmo com limites de token

## ✨ Recursos principais

### Gestão de tarefas
- **Planejamento inteligente**: Análise profunda dos requisitos antes da implementação
- **Decomposição de tarefas**: Divide grandes projetos em unidades atômicas e testáveis
- **Rastreamento de dependências**: Gestão automática de relacionamentos entre tarefas
- **Monitoramento de progresso**: Rastreamento de status e atualizações em tempo real

### Capacidades avançadas
- **🔬 Modo de pesquisa**: Exploração sistemática de tecnologias e soluções
- **🤖 Sistema de agentes**: Atribua agentes IA especializados a tarefas específicas ([Saiba mais](../agents.md))
- **📏 Regras do projeto**: Defina e mantenha padrões de codificação em seu projeto
- **💾 Memória de tarefas**: Backup e restauração automáticos do histórico de tarefas

### Interfaces web

#### 🖥️ Visualizador de tarefas
Interface React moderna para gestão visual de tarefas com arrastar e soltar, busca em tempo real e suporte multi-perfil.

**Configuração rápida:**
```bash
cd tools/task-viewer
npm install
npm run start:all
# Acesso em http://localhost:5173
```

[📖 Documentação completa do visualizador de tarefas](../../tools/task-viewer/README.md)

<kbd><img src="../../tools/task-viewer/task-viewer-interface.png" alt="Interface do visualizador de tarefas" width="600"/></kbd>

#### 🌐 GUI web
Interface web leve opcional para visão geral rápida de tarefas.

Ativar em `.env`: `ENABLE_GUI=true`

## 📚 Documentação

- [📖 Documentação completa](../README.md)
- [🛠️ Ferramentas disponíveis](../tools.md)
- [🤖 Gestão de agentes](../agents.md)
- [🎨 Personalização de prompts](prompt-customization.md)
- [🔧 Referência da API](../api.md)

## 🎯 Casos de uso comuns

<details>
<summary><b>Desenvolvimento de recursos</b></summary>

```
Agente: "plan task: adicionar autenticação de usuário com JWT"
# O agente analisa a base de código, cria subtarefas

Agente: "execute task"
# Implementa a autenticação passo a passo
```
</details>

<details>
<summary><b>Correção de bugs</b></summary>

```
Agente: "plan task: corrigir vazamento de memória no processamento de dados"
# O agente pesquisa o problema, cria plano de correção

Agente: "continuous mode"
# Executa todas as tarefas de correção automaticamente
```
</details>

<details>
<summary><b>Pesquisa e aprendizado</b></summary>

```
Agente: "research: comparar React vs Vue para este projeto"
# Análise sistemática com prós/contras

Agente: "plan task: migrar componente para o framework escolhido"
# Cria plano de migração baseado na pesquisa
```
</details>

## 🛠️ Configuração

### Variáveis de ambiente

Crie um arquivo `.env`:

```bash
# Obrigatório
DATA_DIR=/caminho/para/armazenamento/dados

# Opcional
ENABLE_GUI=true          # Ativar GUI web
WEB_PORT=3000           # Porta web personalizada
PROMPT_LANGUAGE=pt      # Idioma dos prompts (pt, en, zh, etc.)
```

### Comandos disponíveis

| Comando | Descrição |
|---------|-------------|
| `init project rules` | Inicializar padrões do projeto |
| `plan task [descrição]` | Criar um plano de tarefa |
| `execute task [id]` | Executar tarefa específica |
| `continuous mode` | Executar todas as tarefas sequencialmente |
| `list tasks` | Mostrar todas as tarefas |
| `research [tópico]` | Entrar em modo de pesquisa |
| `reflect task [id]` | Revisar e melhorar tarefa |

## 🤝 Contribuindo

Nós acolhemos contribuições! Por favor, consulte nosso [Guia de contribuição](../../CONTRIBUTING.md) para detalhes.

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](../../LICENSE) para detalhes.

## 🌟 Créditos

Criado por [cjo4m06](https://github.com/cjo4m06) e mantido pela comunidade.

---

<p align="center">
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager">GitHub</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/issues">Issues</a> •
  <a href="https://github.com/cjo4m06/mcp-shrimp-task-manager/discussions">Discussões</a>
</p>