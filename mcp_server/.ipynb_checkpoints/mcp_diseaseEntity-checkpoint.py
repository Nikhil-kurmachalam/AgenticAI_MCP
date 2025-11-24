#!/usr/bin/env python3
"""
Mini-PharmAtlas MCP Server
A Model Context Protocol server for querying gene-disease associations
using the NCATS Translator Knowledge Graph (BioThings Explorer).
"""

import asyncio
import json
import httpx
from typing import Any, Sequence, Dict, List, Optional
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import mcp.server.stdio

# Initialize the MCP server
app = Server("mini-pharmatlas")

# Constants
# UPDATED: Using BioThings Explorer (BTE) production endpoint
TRAPI_URL = "https://api.bte.ncats.io/v1/query" 
NCBI_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# ============================================================================
# Async Utility Functions
# ============================================================================

async def query_translator_kg(entrez_id: str) -> Dict[str, Any]:
    """
    Query the NCATS Translator Knowledge Graph via BioThings Explorer (BTE).
    """
    # TRAPI 1.5.0 compliant query
    query = {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": [f"NCBIGene:{entrez_id}"], "categories": ["biolink:Gene"]},
                    "n1": {"categories": ["biolink:Disease"]}
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
        "workflow": [
            {
                "id": "lookup",
            }
        ]
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(TRAPI_URL, json=query)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP Error: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}"}

def extract_disease_associations(kg_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract disease names and evidence from Translator KG results.
    """
    diseases = []
    
    if "error" in kg_result:
        return [{"error": kg_result["error"]}]
    
    try:
        message = kg_result.get("message", {})
        results = message.get("results", [])
        knowledge_graph = message.get("knowledge_graph", {})
        
        # Quick lookup for node info
        nodes_map = knowledge_graph.get("nodes", {})
        
        for result in results:
            node_bindings = result.get("node_bindings", {})
            # We are looking for 'n1' which corresponds to the Disease node
            disease_nodes = node_bindings.get("n1", [])
            
            for disease_node in disease_nodes:
                disease_id = disease_node.get("id")
                
                if disease_id in nodes_map:
                    disease_info = nodes_map[disease_id]
                    disease_name = disease_info.get("name", disease_id)
                    
                    # Avoid duplicates in list
                    if not any(d['disease_id'] == disease_id for d in diseases):
                        diseases.append({
                            "disease_id": disease_id,
                            "disease_name": disease_name,
                            "categories": disease_info.get("categories", [])
                        })
        
        return diseases
    except Exception as e:
        return [{"error": f"Parsing error: {str(e)}"}]

async def get_gene_info(gene_symbol: str) -> Dict[str, Any]:
    """
    Get basic gene information from NCBI Gene API.
    """
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
                return {
                    "gene_symbol": gene_symbol,
                    "entrez_id": id_list[0],
                    "status": "found"
                }
            else:
                return {
                    "gene_symbol": gene_symbol,
                    "status": "not_found"
                }
        except Exception as e:
            return {
                "gene_symbol": gene_symbol,
                "status": "error",
                "error": str(e)
            }

# ============================================================================
# MCP Resource Handlers
# ============================================================================

@app.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="pharmatlas://translator-kg",
            name="NCATS Translator Knowledge Graph",
            mimeType="application/json",
            description="Biomedical knowledge graph for gene-disease associations"
        ),
        Resource(
            uri="pharmatlas://ncbi-gene",
            name="NCBI Gene Database",
            mimeType="application/json",
            description="Gene information and identifiers from NCBI"
        )
    ]

@app.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "pharmatlas://translator-kg":
        return json.dumps({
            "endpoint": TRAPI_URL,
            "description": "NCATS Translator Knowledge Graph (BioThings Explorer)",
            "supported_queries": ["gene-disease associations", "biolink model"]
        }, indent=2)
    elif uri == "pharmatlas://ncbi-gene":
        return json.dumps({
            "endpoint": NCBI_URL,
            "description": "NCBI Gene Database",
            "supported_queries": ["gene ID lookup"]
        }, indent=2)
    else:
        raise ValueError(f"Unknown resource: {uri}")

# ============================================================================
# MCP Tool Handlers
# ============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="find_gene_diseases",
            description="Find diseases associated with a specific gene using the NCATS Translator Knowledge Graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "gene_symbol": {
                        "type": "string",
                        "description": "Gene symbol (e.g., 'APOE', 'APP', 'PSEN1')"
                    }
                },
                "required": ["gene_symbol"]
            }
        ),
        Tool(
            name="get_gene_info",
            description="Get basic information about a gene from NCBI Gene database",
            inputSchema={
                "type": "object",
                "properties": {
                    "gene_symbol": {
                        "type": "string",
                        "description": "Gene symbol (e.g., 'APOE', 'APP', 'PSEN1')"
                    }
                },
                "required": ["gene_symbol"]
            }
        ),
        Tool(
            name="analyze_gene_list",
            description="Analyze a list of genes to find common disease associations",
            inputSchema={
                "type": "object",
                "properties": {
                    "gene_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of gene symbols to analyze"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of genes to analyze",
                        "default": 5
                    }
                },
                "required": ["gene_symbols"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    if name == "find_gene_diseases":
        gene_symbol = arguments.get("gene_symbol", "").upper()
        
        # Step 1: Convert Symbol to ID
        gene_info = await get_gene_info(gene_symbol)
        
        if gene_info.get("status") != "found":
            return [TextContent(type="text", text=f"Could not find gene: {gene_symbol}")]
        
        # Step 2: Query KG
        kg_result = await query_translator_kg(gene_info["entrez_id"])
        diseases = extract_disease_associations(kg_result)
        
        result = {
            "gene": gene_symbol,
            "entrez_id": gene_info["entrez_id"],
            "disease_associations": diseases[:20], # Limit output size for context window
            "total_diseases_found": len(diseases)
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_gene_info":
        gene_symbol = arguments.get("gene_symbol", "").upper()
        gene_info = await get_gene_info(gene_symbol)
        return [TextContent(type="text", text=json.dumps(gene_info, indent=2))]
    
    elif name == "analyze_gene_list":
        gene_symbols = arguments.get("gene_symbols", [])
        limit = arguments.get("limit", 5)
        
        # Cap the limit for safety
        gene_symbols = [g.upper() for g in gene_symbols[:limit]]
        
        results = []
        disease_counts = {}
        
        for gene_symbol in gene_symbols:
            gene_info = await get_gene_info(gene_symbol)
            
            if gene_info.get("status") == "found":
                kg_result = await query_translator_kg(gene_info["entrez_id"])
                diseases = extract_disease_associations(kg_result)
                
                results.append({
                    "gene": gene_symbol,
                    "entrez_id": gene_info["entrez_id"],
                    "disease_count": len(diseases)
                })
                
                for disease in diseases:
                    disease_name = disease.get("disease_name", "Unknown")
                    disease_counts[disease_name] = disease_counts.get(disease_name, 0) + 1
        
        common_diseases = sorted(
            disease_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        summary = {
            "genes_analyzed": gene_symbols,
            "common_diseases": [
                {"disease": d[0], "gene_count": d[1]} for d in common_diseases
            ],
            "details": results
        }
        
        return [TextContent(type="text", text=json.dumps(summary, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    # stdio_server returns a tuple of (read_stream, write_stream)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())