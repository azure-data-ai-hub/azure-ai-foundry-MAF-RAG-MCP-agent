# azure-ai-foundry-MAF-RAG-MCP-agent

## Overview
The `azure-ai-foundry-MAF-RAG-MCP-agent` project demonstrates how to build a Modular Agent Framework (MAF) application that combines Retrieval Augmented Generation (RAG) with the Model Context Protocol (MCP) to expose tools, data sources, and system capabilities to AI agents orchestrated in Azure AI Foundry. It includes:
- Integrated RAG pipeline (ingestion, indexing, retrieval, answer synthesis)
- MCP server & inspector for tool/schema introspection
- Azure AI Foundry agent configuration examples
- Local development & deployment via Azure Functions (`func publish`)
- Extensible plugin/tool architecture

## Architecture
1. **Data Layer**: Documents ingested into a vector store (e.g., Azure AI Search or other embedding store).
2. **Embeddings & Index**: Uses Azure OpenAI / Foundry embedding models for vectorization.
3. **Retrieval**: Semantic + hybrid retrieval to supply context.
4. **Agent Orchestration**: Azure AI Foundry agent configured with MCP tools.
5. **MCP Server**: Exposes tools (search, retrieval, config inspection) and resources following the Model Context Protocol.
6. **Answer Generation**: LLM synthesizes final answer with citations.
7. **Deployment**: Packaged as Azure Functions or container.

## Features
- Pluggable MCP tools (`/tools` directory)
- Unified configuration file (`config/*.json` or `.env`)
- Built-in RAG (chunking, embedding, retrieval)
- MCP Inspector for debugging tool contracts
- Observability hooks (logging, optional OpenTelemetry)

## Prerequisites
- Azure Subscription
- Azure AI Foundry workspace (or Azure OpenAI access)
- Node.js (if MCP server implemented in TS/JS) or Python runtime (depending on implementation)
- Azure Functions Core Tools (`npm i -g azure-functions-core-tools@4`) if using Functions
- `git`, `curl`, `jq` (optional)

## Repository Structure (example)
```text
/README.md
/src/                # Core agent & RAG logic
/src/mcp/            # MCP server implementation & tool adapters
/src/rag/            # Ingestion, chunking, embedding, retrieval logic
/tools/              # Individual MCP tool definitions
/config/             # JSON/YAML configuration templates
/scripts/            # Helper scripts (ingest, reindex, diagnostics)
/azure/              # Infra IaC (Bicep/Terraform) optional
/function/           # Azure Functions entrypoints (if applicable)
.env.example         # Environment variable template
```

Adjust the paths above if your actual structure differs.

## Configuration
You can supply configuration via environment variables or a JSON/YAML file.

### Environment Variables
```bash
AZURE_OPENAI_ENDPOINT=https://<your-endpoint>.openai.azure.com
AZURE_OPENAI_API_KEY=********************************
EMBEDDING_MODEL=text-embedding-3-large # example
CHAT_MODEL=gpt-4o-mini                # example
VECTOR_STORE_TYPE=azure-search        # or cosmos, chroma, pinecone
AZURE_SEARCH_ENDPOINT=https://<search>.search.windows.net
AZURE_SEARCH_API_KEY=********************************
AZURE_SEARCH_INDEX=rag-docs
MAX_RETRIEVAL_RESULTS=8
TEMPERATURE=0.2
```

### Config File (`config/default.json`)
```json
{
  "models": {
    "chat": "gpt-4o-mini",
    "embedding": "text-embedding-3-large"
  },
  "retrieval": {
    "provider": "azure-search",
    "index": "rag-docs",
    "k": 8,
    "filters": {}
  },
  "chunking": {
    "strategy": "recursive",
    "maxTokens": 800,
    "overlap": 80
  },
  "logging": {
    "level": "info"
  }
}
```

### Secrets Management
Use Azure Key Vault for production secrets and map them to environment variables through managed identity.

## RAG Workflow
1. Ingest source documents: `scripts/ingest.sh` (or Python script) performs chunking + embedding.
2. Store embeddings in Azure AI Search index.
3. Query phase retrieves top-k vectors + optional keyword matches.
4. Augment user prompt with retrieved context.
5. LLM generates answer, including citations mapping back to document IDs.

## MCP Server & Inspector
The MCP server hosts: 
- Tool metadata (names, input schema, output schema)
- Resource endpoints (e.g., `/retrieve`, `/search`, `/config`)

### Running MCP Server Locally
```bash
# Install dependencies
npm install   # or pip install -r requirements.txt
# Start server
npm run mcp:dev  # example script
```

### MCP Inspector
Use the MCP Inspector UI to connect to the server and visually explore available tools: parameters, schemas, and sample invocations.
1. Launch MCP Inspector (locally or web).
2. Point it to the MCP server endpoint (e.g., `http://localhost:4000`).
3. Validate tool contracts.
4. Invoke test calls (e.g., `search_documents`, `get_config`).

This helps ensure Azure AI Foundry agents can correctly bind to tool specifications.

## Azure AI Foundry Agent Integration
In Azure AI Foundry, configure the agent: 
- Add model deployment referencing `CHAT_MODEL`.
- Register MCP tools by providing the server URL and tool schema manifest.
- Configure memory & session parameters.
- (Optional) Add system prompt engineering referencing available tools.

### Sample System Prompt Snippet
```text
You are a retrieval-augmented assistant. Before answering, call the `search_documents` tool with relevant keywords. Use the `get_config` tool if you need dynamic thresholds. Cite sources using their `sourceId`.
```

## Local Development
```bash
# Clone
git clone https://github.com/azure-data-ai-hub/azure-ai-foundry-MAF-RAG-MCP-agent.git
cd azure-ai-foundry-MAF-RAG-MCP-agent

# Setup environment
cp .env.example .env
# Edit .env with your keys

# Install deps
npm install   # or pip install -r requirements.txt

# Run ingestion (example)
bash scripts/ingest.sh data/whitepapers/*.pdf

# Start dev server
npm run dev
```

## Azure Functions Deployment (`func publish`)
If packaged as an Azure Function (HTTP trigger exposes MCP endpoints):
```bash
# Login & set subscription
az login
az account set --subscription <SUBSCRIPTION_ID>

# Create function app (Linux, consumption plan example)
az group create -n <rg-name> -l <region>
az storage account create -n <storagename> -g <rg-name> -l <region> --sku Standard_LRS
az functionapp create -n <func-app-name> -g <rg-name> --storage-account <storagename> --consumption-plan-location <region> --runtime node --functions-version 4

# Publish
func azure functionapp publish <func-app-name>
```
After publish, update the MCP server endpoint in Azure AI Foundry agent config to the Function URL.

## Observability & Logging
- Enable Application Insights: set `APPINSIGHTS_INSTRUMENTATIONKEY` env var.
- (Optional) OpenTelemetry exporter for traces on tool invocations.

## Testing
- Unit tests: `npm test` or `pytest`
- Integration (RAG): run retrieval tests verifying latency & accuracy.
- Contract tests: Validate MCP tool JSON schema with inspector.

## Security & Compliance
- Use managed identity for Azure Search & Key Vault.
- Avoid storing raw PII in logs.
- Implement rate limiting if exposing public endpoints.

## Troubleshooting
| Symptom | Cause | Resolution |
|--------|-------|------------|
| Empty retrieval results | Index not built | Re-run ingestion script |
| 401 from Azure OpenAI | Invalid key or endpoint | Verify env vars / Key Vault references |
| Tool not visible in Inspector | Server not started / CORS | Check logs, enable CORS headers |
| High latency | Large k or slow embedding model | Reduce k, cache embeddings |

## Extending Tools
Add new tool in `tools/` implementing MCP contract: 
```ts
export const newTool = {
  name: 'summarize_document',
  inputSchema: { type: 'object', properties: { docId: { type: 'string' } }, required: ['docId'] },
  outputSchema: { type: 'object', properties: { summary: { type: 'string' } } },
  execute: async (args, ctx) => { /* ... */ }
};
```
Register it in the server bootstrap and redeploy.

## Roadmap
- Vector store abstraction improvements
- Advanced re-ranking (Reciprocal Rank Fusion)
- Caching layer for frequent queries
- Streaming responses

## Contributing
Pull requests welcome. Please open an issue to discuss major changes first.

1. Fork repo
2. Create feature branch
3. Commit with conventional messages
4. Open PR

## License
Specify your license here (e.g., MIT).

## Disclaimer
This README may contain placeholders (model names, endpoints). Replace them with your actual configuration before production use.
