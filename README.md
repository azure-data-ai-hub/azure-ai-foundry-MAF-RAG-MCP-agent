# azure-ai-foundry-MAF-RAG-MCP-agent

## Overview
The `azure-ai-foundry-MAF-RAG-MCP-agent` project demonstrates how to build a Modular Agent Framework (MAF) application that combines Retrieval Augmented Generation (RAG) with the Model Context Protocol (MCP) to expose tools, data sources, and system capabilities to AI agents orchestrated in Azure AI Foundry.

It includes:
- Integrated RAG pipeline (ingestion, indexing, retrieval, answer synthesis)
- MCP server & inspector for tool/schema introspection
- Azure AI Foundry agent configuration examples
- Local development & deployment via Azure Functions (`func publish`)
- Extensible plugin/tool architecture
- Dual implementation patterns (Node.js & Python) where applicable

## Quick Start
```bash
# Clone
git clone https://github.com/azure-data-ai-hub/azure-ai-foundry-MAF-RAG-MCP-agent.git
cd azure-ai-foundry-MAF-RAG-MCP-agent

# Copy env template and edit
cp .env.example .env
$EDITOR .env

# Install (Node variant)
npm install
# OR (Python variant)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Ingest sample docs
bash scripts/ingest.sh data/*.pdf

# Run dev MCP server
npm run mcp:dev   # or: python src/mcp/server.py
```

## Architecture
```text
┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│  Source Docs   │ -> │ Chunk & Embedding │ -> │  Vector Index      │
└────────────────┘    └──────────────────┘    └────────────────────┘
         ↓                     ↑                         ↓
   scripts/ingest         Embedding Model          Semantic / Hybrid
         ↓                                            Retrieval (k)
┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│ Azure AI Agent │ -> │ MCP Tools Layer  │ -> │ RAG Context Builder │
└────────────────┘    └──────────────────┘    └────────────────────┘
                               ↓
                        LLM Answer Synth
```
1. Data Layer: Documents ingested into a vector store (Azure AI Search or alternative) via ingestion script.
2. Embeddings: Generated using Azure OpenAI / Foundry deployments.
3. Retrieval: Semantic + optional keyword/hybrid retrieval feeding top-k chunks.
4. MCP Server: Exposes standardized tools for retrieval, search, config, health.
5. Azure AI Foundry Agent: Orchestrates tool calls + system prompting.
6. Answer Generation: LLM composes final response with citations.
7. Deployment: Azure Functions / Container App / VM.

## Repository Structure (illustrative)
```text
/README.md
/src/
  mcp/              # MCP server + tool registration
  rag/              # RAG pipeline modules
  utils/            # Shared helpers
/tools/             # Discrete MCP tool definitions
/config/            # JSON/YAML config sets
/scripts/           # ingest.sh, reindex.sh, benchmark.sh
/function/          # Azure Functions bindings (if used)
/infra/             # Bicep/Terraform templates
/tests/             # Unit + integration tests
.env.example        # Environment template
```

## MCP Tool Manifest Example
```json
{
  "version": "1.0.0",
  "tools": [
    {
      "name": "search_documents",
      "description": "Retrieve relevant document chunks via semantic vector search.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" },
          "k": { "type": "integer", "default": 6 }
        },
        "required": ["query"]
      },
      "outputSchema": {
        "type": "object",
        "properties": {
          "results": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "chunk": { "type": "string" },
                "score": { "type": "number" },
                "sourceId": { "type": "string" }
              }
            }
          }
        }
      }
    }
  ]
}
```

## Configuration
### Environment Variables (minimal)
```bash
AZURE_OPENAI_ENDPOINT=https://<your-endpoint>.openai.azure.com
AZURE_OPENAI_API_KEY=********************************
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-large
VECTOR_STORE_TYPE=azure-search
AZURE_SEARCH_ENDPOINT=https://<search>.search.windows.net
AZURE_SEARCH_API_KEY=********************************
AZURE_SEARCH_INDEX=rag-docs
MAX_RETRIEVAL_RESULTS=8
TEMPERATURE=0.2
APPINSIGHTS_INSTRUMENTATIONKEY=<optional>
```

### JSON Config (`config/default.json`)
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
    "hybrid": true,
    "filters": {}
  },
  "chunking": {
    "strategy": "recursive",
    "maxTokens": 800,
    "overlap": 80
  },
  "rerank": {
    "enabled": false,
    "model": "text-embedding-3-large"
  },
  "cache": {
    "enabled": true,
    "ttlSeconds": 900
  },
  "logging": {
    "level": "info"
  }
}
```

### Secrets Management
Use Azure Key Vault + Managed Identity for production. Avoid committing secrets. For local dev use `.env` only.

## Ingestion Workflow
```bash
# Example ingestion (PDF -> chunks -> embeddings -> index)
INGEST_SOURCE=./data/whitepapers/*.pdf
python scripts/ingest.py --source "$INGEST_SOURCE" \
  --index "$AZURE_SEARCH_INDEX" \
  --embedding-model "$AZURE_OPENAI_EMBED_DEPLOYMENT" \
  --chunk-strategy recursive --chunk-size 800 --overlap 80
```
Steps:
1. Read & normalize documents (PDF/HTML/MD).
2. Split into semantic chunks.
3. Generate embeddings.
4. Upsert to vector index with metadata (sourceId, page, hash).

## Retrieval Flow (Runtime)
1. Agent receives user query.
2. Calls `search_documents` (MCP tool) with query/k.
3. (Optional) Calls `get_config` for dynamic parameters.
4. Combines top-k chunks into context window (trimming by token budget).
5. Calls chat model with system + user + context.
6. Returns answer with citations mapping `sourceId`.

## MCP Server & Inspector
Run locally:
```bash
npm run mcp:dev
# or
python src/mcp/server.py
```
Use MCP Inspector GUI:
1. Start Inspector.
2. Enter server endpoint: `http://localhost:4000` (or function URL).
3. Enumerate tools, validate schemas.
4. Test invocation payloads before integrating into Azure AI Foundry.

## Azure Functions Deployment (`func publish`)
```bash
az login
az account set --subscription <SUB_ID>
az group create -n <rg-name> -l <region>
az storage account create -n <storagename> -g <rg-name> -l <region> --sku Standard_LRS
az functionapp create -n <func-app-name> -g <rg-name> --storage-account <storagename> --consumption-plan-location <region> --runtime node --functions-version 4
func azure functionapp publish <func-app-name>
```
Update agent configuration with published Function URL for MCP endpoint.

## Container Deployment (Alternative)
```bash
docker build -t maf-rag-mcp:latest .
docker run -p 4000:4000 --env-file .env maf-rag-mcp:latest
```
Push to Azure Container Registry & deploy to Azure Container Apps if needed.

## Observability & Metrics
- Application Insights telemetry (requests, dependencies, traces)
- Optional OpenTelemetry exporter for spans on tool calls
- Latency SLO: < 2s retrieval, < 6s total response (adjust for model)

## Performance Tuning
| Area | Lever | Impact |
|------|-------|--------|
| Retrieval latency | Reduce k | Faster first token |
| Context relevance | Enable rerank | Higher answer quality |
| Token cost | Shorter chunks | Lower prompt size |
| Cold start | Preload embeddings cache | Lower first request latency |
| Index size | Periodic compaction | Stable performance |

## Testing Strategy
- Unit: chunking logic, embedding wrappers
- Integration: end-to-end query -> answer -> citations
- Contract: JSON schema of tools vs Inspector responses
- Load: k6 or locust to simulate concurrent queries

## Security & Compliance
- Principle of least privilege on Search index access
- Managed Identity > static keys
- Log scrubbing of PII & secrets
- Rate limiting (Functions middleware or reverse proxy)

## Troubleshooting
| Symptom | Cause | Resolution |
|---------|-------|------------|
| Empty results | Index stale or misconfigured | Re-run ingestion, verify index name |
| 401 Azure OpenAI | Bad key / identity not assigned | Check Key Vault & identity roles |
| Tool absent | Server not exporting manifest | Inspect server startup logs |
| High latency | Oversized context / k too high | Reduce k or chunk size |
| Memory errors | Large PDF ingestion | Stream & batch embeddings |

## Extending Tools
Example (TypeScript):
```ts
export const summarize_document = {
  name: 'summarize_document',
  inputSchema: {
    type: 'object',
    properties: { docId: { type: 'string' } },
    required: ['docId']
  },
  outputSchema: {
    type: 'object',
    properties: { summary: { type: 'string' }, sourceId: { type: 'string' } }
  },
  execute: async (args, ctx) => {
    const doc = await ctx.store.get(args.docId);
    const summary = await ctx.llm.summarize(doc.text);
    return { summary, sourceId: args.docId };
  }
};
```
Register new tool in server bootstrap and redeploy / republish.

## Sample System Prompt (Extended)
```text
You are a retrieval-augmented assistant. For each user query: 1) Call search_documents unless the query is purely conversational. 2) Use get_config to adjust retrieval k if query complexity is high. 3) Cite sources using [sourceId]. If you cannot retrieve relevant context, ask clarifying questions.
```

## Roadmap
- Vector store abstraction improvements
- Advanced re-ranking (Reciprocal Rank Fusion)
- Caching layer for frequent queries
- Streaming responses
- Multi-tenant workspace support
- Metadata filters (date range, taxonomy)

## Contributing
Pull requests welcome. Please open an issue to discuss major changes first.
1. Fork
2. Branch (`feat/<name>`)
3. Commit (Conventional Commits)
4. PR + link related issues
5. Review + merge

## FAQ
**Q: Why MCP?** Standardizes tool interfaces enabling plug & play agent orchestration.
**Q: Can I swap vector store?** Yes; implement provider adapter & map to retrieval tool.
**Q: How big should chunks be?** 500-1000 tokens typical; adjust for model context window.
**Q: Support streaming?** Planned via server-sent events upgrade.

## License
MIT

## Disclaimer
Replace placeholders (model names, endpoints, indices) with production values. Review security recommendations before external exposure.
