import azure.functions as func
import logging
import json
import asyncio
import os
from typing import List, Dict

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import QueryType

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.mcp_tool_trigger(
    tool_name="getTagLine",
    arg_name="context",
    description="Returns the official tagline (mission statement) for a given product.",
)
async def MyPythonMcpTool(context) -> func.HttpResponse:
    logging.info("Context Passed" + str(context))
    async with (
            DefaultAzureCredential() as identity_credential,
            AzureAIAgentClient(async_credential=identity_credential, project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")) as chat_client,
        ):

        try:
            async with ChatAgent(
                chat_client=chat_client,
                # Instructions here are applicable only to this ChatAgent instance
                # These instructions will be combined with instructions on existing remote agent.
                # The final instructions during the execution will look like:
                # "'End each response with [END]. Respond with 'Hello World' only'"
                instructions="You are an expert tag line generator for products.  Generate tag line given the product name",
            ) as agent:
                contextJson = json.loads(context)
                arguments = contextJson.get("arguments", {})
                query = arguments.get("productName", "Unknown Product")

                logging.info(f"Product Name: {query}")
                result = await agent.run(query)
                logging.info(f"Agent: {result}")
        except Exception as e:
            logging.error(f"Error during tagline generation: {e}")
            result = "Error occurred during tagline generation."

    return json.dumps({"tagline": str(result)})


@app.mcp_tool_trigger(
    tool_name="getContractAnalysis",
    arg_name="context",
    description="Returns the analysis of a given contract.",
)
async def ContractAnalysisTool(context) -> func.HttpResponse:
    logging.info("Context Passed" + str(context))

    contractAnalysisAgentID =os.environ["CONTRACT_ANALYSIS_AGENT_ID"]
    async with (
        DefaultAzureCredential() as credential,
        AzureAIAgentClient(async_credential=credential, project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"), agent_id=contractAnalysisAgentID) as chat_client,
    ):
        try:
            async with ChatAgent(
                chat_client=chat_client,
                # Instructions here are applicable only to this ChatAgent instance
                # These instructions will be combined with instructions on existing remote agent.
                # The final instructions during the execution will look like:
                # "'End each response with [END]. Respond with 'Hello World' only'"
                instructions="You are an expert contract analyst.  Analyze the given contract text.",
            ) as agent:
                contextJson = json.loads(context)
                arguments = contextJson.get("arguments", {})
                contractName = arguments.get("contractName", "Unknown Contract")
                
                logging.info(f"Contract Name: {contractName}")

                result = await agent.run(contractName)
                logging.info(f"Agent: {result}")
        except Exception as e:
            logging.error(f"Error during contract analysis: {e}")
            result = "Error occurred during contract analysis."

    return json.dumps({"analysis": str(result)})


@app.route(route="contract-analysis", methods=[func.HttpMethod.GET])
async def contract_analysis_route(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP endpoint that proxies contract analysis requests to Microsoft Agentic Framework."""
    contract_name = req.params.get("contractName")
    payload = None
    if not contract_name:
        try:
            payload = req.get_json()
        except ValueError:
            payload = None
        except Exception as ex:  # noqa: BLE001 - match runtime behavior
            logging.warning("Unexpected payload parsing issue: %s", ex)
            payload = None

    contract_name = contract_name or (payload or {}).get("contractName")
    if not contract_name:
        logging.info("contract-analysis request missing 'contractName' parameter.")
        return func.HttpResponse(
            json.dumps({"error": "Provide a 'contractName' query parameter."}),
            status_code=400,
            mimetype="application/json",
        )

    contract_agent_id = os.getenv("CONTRACT_ANALYSIS_AGENT_ID")
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    missing_settings: List[str] = [
        name
        for name, value in {
            "CONTRACT_ANALYSIS_AGENT_ID": contract_agent_id,
            "AZURE_AI_PROJECT_ENDPOINT": project_endpoint,
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_name,
        }.items()
        if not value
    ]

    if missing_settings:
        logging.error("Missing configuration for contract-analysis: %s", ", ".join(missing_settings))
        return func.HttpResponse(
            json.dumps({
                "error": "Missing configuration settings.",
                "missing": missing_settings,
            }),
            status_code=500,
            mimetype="application/json",
        )

    try:
        async with (
            DefaultAzureCredential() as identity_credential,
            AzureAIAgentClient(async_credential=identity_credential, project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"), agent_id=contract_agent_id) as chat_client,
        ):
            async with ChatAgent(
                chat_client=chat_client,
                instructions=(
                    "You are an expert contract analyst. Analyze the given contract text."
                ),
            ) as agent:
                analysis = await agent.run(contract_name)
    except (ClientAuthenticationError, HttpResponseError) as ex:
        logging.error("Azure AI project call failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "Azure AI project call failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )
    except Exception as ex:  # noqa: BLE001 - sanitized error for caller
        logging.error("Contract analysis agent execution failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "Contract analysis failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({"analysis": str(analysis)}),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="rag-query", methods=[func.HttpMethod.GET])
async def run_rag_query(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP endpoint that performs retrieval augmented generation via Azure AI Search."""
    question = req.params.get("question")
    payload = None
    if not question:
        try:
            payload = req.get_json()
        except ValueError:
            payload = None
        except Exception as ex:  # noqa: BLE001 - align with runtime behavior for non-JSON bodies
            logging.warning("Unexpected payload parsing issue: %s", ex)
            payload = None

    question = question or (payload or {}).get("question")
    if not question:
        logging.info("rag-query request missing 'question' parameter.")
        return func.HttpResponse(
            json.dumps({"error": "Provide a 'question' query parameter."}),
            status_code=400,
            mimetype="application/json",
        )

    search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    search_index = os.getenv("AZURE_SEARCH_INDEX_NAME")
    missing_settings: List[str] = [
        name
        for name, value in {
            "AZURE_SEARCH_ENDPOINT": search_endpoint,
            "AZURE_SEARCH_INDEX_NAME": search_index,
            "AZURE_AI_PROJECT_ENDPOINT": os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        }.items()
        if not value
    ]

    if missing_settings:
        logging.error("Missing configuration for rag-query: %s", ", ".join(missing_settings))
        return func.HttpResponse(
            json.dumps({
                "error": "Missing configuration settings.",
                "missing": missing_settings,
            }),
            status_code=500,
            mimetype="application/json",
        )

    semantic_config = os.getenv("AZURE_SEARCH_SEMANTIC_CONFIG")
    content_field = os.getenv("AZURE_SEARCH_CONTENT_FIELD", "content")
    top_k = int(os.getenv("AZURE_SEARCH_TOP_K", "3"))

    retrieved_docs: List[Dict[str, str]] = []

    try:
        async with DefaultAzureCredential() as search_credential:
            async with SearchClient(
                endpoint=search_endpoint,
                index_name=search_index,
                credential=search_credential,
            ) as search_client:
                search_kwargs = {
                    "search_text": question,
                    "top": top_k,
                }
                if semantic_config:
                    search_kwargs.update(
                        {
                            "query_type": QueryType.SEMANTIC,
                            "semantic_configuration_name": semantic_config,
                        }
                    )

                result_pager = await search_client.search(**search_kwargs)
                async for doc in result_pager:
                    content_value = doc.get(content_field)
                    if not content_value:
                        continue
                    retrieved_docs.append(
                        {
                            "content": content_value,
                            "source": doc.get("source", doc.get("id", "")),
                        }
                    )
                    if len(retrieved_docs) >= top_k:
                        break
    except (ClientAuthenticationError, HttpResponseError) as ex:
        logging.error("Azure AI Search query failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "Azure AI Search query failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )

    if not retrieved_docs:
        logging.info("No documents retrieved for question: %s", question)
        return func.HttpResponse(
            json.dumps({"answer": "", "sources": [], "message": "No relevant documents found."}),
            status_code=200,
            mimetype="application/json",
        )

    composed_context = "\n\n".join(
        f"Source: {doc['source']}\n{doc['content']}" for doc in retrieved_docs
    )

    try:
        async with (
            DefaultAzureCredential() as identity_credential,
            AzureAIAgentClient(async_credential=identity_credential, project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")) as chat_client,
        ):
            try:
                async with ChatAgent(
                    chat_client=chat_client,
                    instructions=(
                        "Answer using the supplied context. If the answer is not present, say you do not know."  # context-specific reminder
                    ),
                ) as agent:
                    prompt = (
                        "You are assisting with retrieval augmented generation."
                        "\n\nContext:\n"
                        f"{composed_context}\n\nQuestion: {question}"
                    )
                    answer = await agent.run(prompt)
            except Exception as agent_ex:
                logging.error("Agent processing failed: %s", agent_ex)
    except Exception as ex:  # noqa: BLE001 - returning sanitized error to caller
        logging.error("Agent execution failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "Agent execution failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )

    response_body = {
        "answer": str(answer),
        "sources": retrieved_docs,
    }

    return func.HttpResponse(
        json.dumps(response_body),
        status_code=200,
        mimetype="application/json",
    )