import azure.functions as func
import logging
import json
import asyncio
import os
from typing import List, Dict, Any
from tool_helpers import ToolProperty, ToolPropertyList  # Helper classes for tool definitions
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import QueryType
from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import (
    ListSortOrder,
    McpTool,
    RequiredMcpToolCall,
    RunStepActivityDetails,
    SubmitToolApprovalAction,
    ToolApproval,
)

tool_properties_get_contract_analysis = ToolPropertyList(
    ToolProperty("contractName", "string", "Identifier or name of the contract to analyze."),
)

tool_properties_get_tagline = ToolPropertyList(
    ToolProperty("productName", "string", "Name of the product that needs a tagline."),
)


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.mcp_tool_trigger(
    tool_name="getTagLine",
    arg_name="context",
    description="Returns the official tagline (mission statement) for a given product.",
    tool_properties=tool_properties_get_tagline.to_json(),
)
async def MyPythonMcpTool(context: str) -> func.HttpResponse:
    logging.info("Context Passed %s", context)
    try:
        context_payload = json.loads(context) if context else {}
    except json.JSONDecodeError as decode_error:
        logging.error("Invalid JSON payload for getTagLine tool: %s", decode_error)
        context_payload = {}

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
                arguments = (context_payload or {}).get("arguments", {})
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
    tool_properties=tool_properties_get_contract_analysis.to_json(),
)
async def ContractAnalysisTool(context: str) -> func.HttpResponse:
    logging.info("Context Passed %s", context)

    try:
        context_payload = json.loads(context) if context else {}
    except json.JSONDecodeError as decode_error:
        logging.error("Invalid JSON payload for getContractAnalysis tool: %s", decode_error)
        context_payload = {}

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
                arguments = (context_payload or {}).get("arguments", {})
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

@app.route(route="run-mcp-agent", methods=[func.HttpMethod.GET])
async def run_mcp_agent(req: func.HttpRequest) -> func.HttpResponse:
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
        logging.info("run-mcp-agent request missing 'question' parameter.")
        return func.HttpResponse(
            json.dumps({"error": "Provide a 'question' query parameter."}),
            status_code=400,
            mimetype="application/json",
        )

    mcp_server_url = os.environ.get("MCP_SERVER_URL")
    mcp_server_label = os.environ.get("MCP_SERVER_LABEL", "AzureMCPServer")
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")

    missing_settings: List[str] = [
        name
        for name, value in {
            "MCP_SERVER_URL": mcp_server_url,
            "AZURE_AI_PROJECT_ENDPOINT": project_endpoint,
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_name,
        }.items()
        if not value
    ]

    if missing_settings:
        logging.error("Missing configuration for run-mcp-agent: %s", ", ".join(missing_settings))
        return func.HttpResponse(
            json.dumps({
                "error": "Missing configuration settings.",
                "missing": missing_settings,
            }),
            status_code=500,
            mimetype="application/json",
        )

    mcp_tool = McpTool(
        server_label=mcp_server_label,
        server_url=mcp_server_url,
        allowed_tools=[],
    )

    assistant_answer = ""
    conversation: List[Dict[str, str]] = []
    run_status = "failed"
    run_id = None
    run_error = None

    try:
        async with DefaultAzureCredential() as identity_credential:
            async with AIProjectClient(endpoint=project_endpoint, credential=identity_credential) as project_client:
                agents_client = project_client.agents

                agent = await agents_client.create_agent(
                    model=model_name,
                    name="my-mcp-agent",
                    instructions=(
                        "You are a helpful agent that can use MCP tools to assist users. "
                        "Use the available MCP tools to answer questions and perform tasks."
                    ),
                    tools=mcp_tool.definitions,
                )

                logging.info("Created agent, ID: %s", agent.id)
                logging.info("MCP Server: %s at %s", mcp_tool.server_label, mcp_tool.server_url)

                thread = await agents_client.threads.create()
                logging.info("Created thread, ID: %s", thread.id)

                message = await agents_client.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=question,
                )
                logging.info("Created message, ID: %s", message.id)

                mcp_tool.update_headers("x-functions-key", os.environ["MCP_EXTENSION_KEY"])

                run = await agents_client.runs.create(
                    thread_id=thread.id,
                    agent_id=agent.id,
                    tool_resources=mcp_tool.resources,
                )
                run_id = run.id
                logging.info("Created run, ID: %s", run.id)

                while run.status in {"queued", "in_progress", "requires_action"}:
                    await asyncio.sleep(1)
                    run = await agents_client.runs.get(thread_id=thread.id, run_id=run.id)

                    if run.status == "requires_action" and isinstance(run.required_action, SubmitToolApprovalAction):
                        tool_calls = run.required_action.submit_tool_approval.tool_calls
                        if not tool_calls:
                            logging.info("No tool calls provided - cancelling run")
                            await agents_client.runs.cancel(thread_id=thread.id, run_id=run.id)
                            break

                        tool_approvals = []
                        for tool_call in tool_calls:
                            if isinstance(tool_call, RequiredMcpToolCall):
                                try:
                                    logging.info("Approving tool call: %s", tool_call)
                                    tool_approvals.append(
                                        ToolApproval(
                                            tool_call_id=tool_call.id,
                                            approve=True,
                                            headers=mcp_tool.headers,
                                        )
                                    )
                                except Exception as approval_error:  # noqa: BLE001
                                    logging.info(
                                        "Error approving tool_call %s: %s",
                                        tool_call.id,
                                        approval_error,
                                    )

                        logging.info("tool_approvals: %s", tool_approvals)
                        if tool_approvals:
                            await agents_client.runs.submit_tool_outputs(
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_approvals=tool_approvals,
                            )

                    logging.info("Current run status: %s", run.status)

                run_status = run.status
                if run.status == "failed":
                    run_error = run.last_error
                    logging.info("Run failed: %s", run_error)
                else:
                    logging.info("Run completed with status: %s", run.status)

                run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
                async for step in run_steps:
                    logging.info("Step %s status: %s", step["id"], step["status"])
                    step_details = step.get("step_details", {})
                    tool_calls = step_details.get("tool_calls", [])

                    if tool_calls:
                        logging.info("  MCP Tool calls:")
                        for call in tool_calls:
                            logging.info("    Tool Call ID: %s", call.get("id"))
                            logging.info("    Type: %s", call.get("type"))

                    if isinstance(step_details, RunStepActivityDetails):
                        for activity in step_details.activities:
                            for function_name, function_definition in activity.tools.items():
                                logging.info(
                                    "  The function %s with description \"%s\" will be called.",
                                    function_name,
                                    function_definition.description,
                                )
                                if function_definition.parameters.properties:
                                    logging.info("  Function parameters:")
                                    for argument, func_argument in function_definition.parameters.properties.items():
                                        logging.info("      %s", argument)
                                        logging.info("      Type: %s", func_argument.type)
                                        logging.info("      Description: %s", func_argument.description)
                                else:
                                    logging.info("This function has no parameters")

                messages = agents_client.messages.list(
                    thread_id=thread.id,
                    order=ListSortOrder.ASCENDING,
                )
                logging.info("\nConversation:")
                logging.info("-" * 50)
                async for msg in messages:
                    text_value = ""
                    if msg.text_messages:
                        last_text = msg.text_messages[-1]
                        text_value = last_text.text.value
                        logging.info("%s: %s", msg.role.upper(), text_value)
                        logging.info("-" * 50)

                    if text_value:
                        conversation.append({"role": msg.role, "text": text_value})
                        if msg.role == "assistant":
                            assistant_answer = text_value

                logging.info("Current allowed tools: %s", mcp_tool.allowed_tools)

                await agents_client.delete_agent(agent.id)
                logging.info("Deleted agent")
    except (ClientAuthenticationError, HttpResponseError) as ex:
        logging.error("Azure AI project call failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "Azure AI project call failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )
    except Exception as ex:  # noqa: BLE001
        logging.error("run-mcp-agent execution failed: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": "run-mcp-agent execution failed.", "details": str(ex)}),
            status_code=502,
            mimetype="application/json",
        )

    response_body: Dict[str, object] = {
        "answer": assistant_answer,
        "runStatus": run_status,
        "runId": run_id,
        "conversation": conversation,
    }
    if run_error:
        response_body["runError"] = str(run_error)

    return func.HttpResponse(
        json.dumps(response_body),
        status_code=200,
        mimetype="application/json",
    )