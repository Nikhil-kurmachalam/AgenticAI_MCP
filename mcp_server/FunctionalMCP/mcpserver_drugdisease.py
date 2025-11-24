
#!/usr/bin/env python3
"""
Mini-PharmAtlas MCP Server
A Model Context Protocol server for querying gene-disease AND gene-drug associations.
"""

import asyncio
import json
import httpx
from typing import Any, Sequence, Dict, List, Optional
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent
)
import mcp.server.stdio

app = Server("mini-pharmatlas")

# Constants
TRAPI_URL = "https://api.bte.ncats.io/v1/query" 
NCBI_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# ============================================================================
# Async Utility Functions
# ============================================================================

async def query_translator_kg(entrez_id: str, target_category: str) -> Dict[str, Any]:
    """
    Query BioThings Explorer. 
    target_category should be 'biolink:Disease' or 'biolink:ChemicalEntity'
    """
    # We use 'ChemicalEntity' because it catches Drugs, Small Molecules, and Metabolites
    
    query = {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": [f"NCBIGene:{entrez_id}"], "categories": ["biolink:Gene"]},
                    "n1": {"categories": [target_category]} 
                },
                "edges": {
                    "e01": {
                        "subject": "n0",
                        "object": "n1",
                        "predicates": ["biolink:related_to"]
                    }
                }
            }
        },
        "workflow": [{"id": "lookup"}]
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(TRAPI_URL, json=query)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"Connection error: {str(e)}"}

def extract_associations(kg_result: Dict[str, Any], type_label: str) -> List[Dict[str, Any]]:
    """
    Generic function to extract names (Disease or Drug) from results.
    """
    items = []
    
    if "error" in kg_result:
        return [{"error": kg_result["error"]}]
    
    try:
        message = kg_result.get("message", {})
        results = message.get("results", [])
        knowledge_graph = message.get("knowledge_graph", {})
        nodes_map = knowledge_graph.get("nodes", {})
        
        for result in results:
            node_bindings = result.get("node_bindings", {})
            # 'n1' is the target node (the Disease or the Drug)
            target_nodes = node_bindings.get("n1", [])
            
            for node in target_nodes:
                node_id = node.get("id")
                
                if node_id in nodes_map:
                    node_info = nodes_map[node_id]
                    node_name = node_info.get("name", node_id)
                    
                    # Avoid duplicates
                    if not any(i['id'] == node_id for i in items):
                        items.append({
                            "id": node_id,
                            "name": node_name,
                            "type": type_label, # e.g., "Disease" or "Drug"
                            "categories": node_info.get("categories", [])
                        })
        return items
    except Exception as e:
        return [{"error": f"Parsing error: {str(e)}"}]

async def get_gene_info(gene_symbol: str) -> Dict[str, Any]:
    """Get NCBI Gene ID from Symbol"""
    params = {
        "db": "gene",
        "term": f"{gene_symbol}[Gene Name] AND Homo sapiens[Organism]",
        "retmode": "json",
        "retmax": 1
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(NCBI_URL, params=params)
            response.raise_for_status()
            data = response.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if id_list:
                return {"gene_symbol": gene_symbol, "entrez_id": id_list[0], "status": "found"}
            else:
                return {"gene_symbol": gene_symbol, "status": "not_found"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

# ============================================================================
# MCP Tool Handlers
# ============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="find_gene_interactions",
            description="Find both Diseases AND Drugs associated with a specific gene.",
            inputSchema={
                "type": "object",
                "properties": {
                    "gene_symbol": {
                        "type": "string",
                        "description": "Gene symbol (e.g., 'APOE', 'TNF')"
                    }
                },
                "required": ["gene_symbol"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    if name == "find_gene_interactions":
        gene_symbol = arguments.get("gene_symbol", "").upper()
        
        # 1. Get ID
        gene_info = await get_gene_info(gene_symbol)
        if gene_info.get("status") != "found":
            return [TextContent(type="text", text=f"Could not find gene: {gene_symbol}")]
        
        entrez_id = gene_info["entrez_id"]

        # 2. Run TWO queries at the same time (Async Magic!)
        # We ask for Diseases AND ChemicalEntities (Drugs) simultaneously
        print(f"Fetching data for {gene_symbol}...") # Logs to console (invisible to Claude usually)
        
        task1 = query_translator_kg(entrez_id, "biolink:Disease")
        task2 = query_translator_kg(entrez_id, "biolink:ChemicalEntity")
        
        # await asyncio.gather waits for both to finish
        disease_raw, drug_raw = await asyncio.gather(task1, task2)
        
        # 3. Clean results
        diseases = extract_associations(disease_raw, "Disease")
        drugs = extract_associations(drug_raw, "Drug")
        
        # 4. Format output
        result = {
            "gene": gene_symbol,
            "entrez_id": entrez_id,
            "summary": {
                "disease_count": len(diseases),
                "drug_count": len(drugs)
            },
            "top_diseases": diseases[:15], # Limit to save space
            "top_drugs": drugs[:15]        # Limit to save space
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())