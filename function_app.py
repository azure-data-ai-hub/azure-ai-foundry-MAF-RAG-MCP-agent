import azure.functions as func
import logging
import json
import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.mcp_tool_trigger(
    tool_name="getTagLine",
    arg_name="context",
    description="Returns the official tagline (mission statement) for a given product.",
)
async def MyPythonMcpTool(context) -> func.HttpResponse:
    logging.info("Context Passed" + str(context))
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as client,
    ):
        azure_ai_agent = await client.agents.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            # Create remote agent with default instructions
            # These instructions will persist on created agent for every run.
            instructions="You are an expert tag line generator for products.  Generate tag line given the product name",
        )

        chat_client = AzureAIAgentClient(project_client=client, agent_id=azure_ai_agent.id)

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
        finally:
            # Clean up the agent manually
            await client.agents.delete_agent(azure_ai_agent.id)

    return json.dumps({"tagline": str(result)})


@app.mcp_tool_trigger(
    tool_name="getContractAnalysis",
    arg_name="context",
    description="Returns the analysis of a given contract.",
)
async def ContractAnalysisTool(context) -> func.HttpResponse:
    logging.info("Context Passed" + str(context))

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as client,
    ):

        contractAnalysisAgentID =os.environ["CONTRACT_ANALYSIS_AGENT_ID"]
        chat_client = AzureAIAgentClient(project_client=client, agent_id=contractAnalysisAgentID)
        

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