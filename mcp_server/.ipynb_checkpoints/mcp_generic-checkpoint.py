#!/usr/bin/env python3
"""
Mini-PharmAtlas MCP Server
A Model Context Protocol server for querying gene-disease associations
using the NCATS Translator Knowledge Graph.
"""

import asyncio
import json
import requests
from typing import Any, Sequence
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


# ============================================================================
# Utility Functions (from your Week 2 work)
# ============================================================================

def query_translator_kg(gene_name: str) -> dict:
    """
    Query the NCATS Translator Knowledge Graph for disease associations.
    
    Args:
        gene_name: Gene symbol (e.g., 'APOE')
    
    Returns:
        dict: Query results from Translator KG
    """
    url = "https://aragorn.renci.org/1.4/query"
    
    query = {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": [f"NCBIGene:{gene_name}"], "categories": ["biolink:Gene"]},
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
        }
    }
    
    try:
        response = requests.post(url, json=query, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def extract_disease_associations(kg_result: dict) -> list:
    """
    Extract disease names and evidence from Translator KG results.
    
    Args:
        kg_result: Raw response from Translator KG
    
    Returns:
        list: List of disease associations with evidence
    """
    diseases = []
    
    if "error" in kg_result:
        return [{"error": kg_result["error"]}]
    
    try:
        results = kg_result.get("message", {}).get("results", [])
        knowledge_graph = kg_result.get("message", {}).get("knowledge_graph", {})
        
        for result in results:
            node_bindings = result.get("node_bindings", {})
            disease_nodes = node_bindings.get("n1", [])
            
            for disease_node in disease_nodes:
                disease_id = disease_node.get("id")
                
                # Get disease info from knowledge graph
                if disease_id in knowledge_graph.get("nodes", {}):
                    disease_info = knowledge_graph["nodes"][disease_id]
                    disease_name = disease_info.get("name", disease_id)
                    
                    diseases.append({
                        "disease_id": disease_id,
                        "disease_name": disease_name,
                        "categories": disease_info.get("categories", [])
                    })
        
        return diseases
    except Exception as e:
        return [{"error": f"Parsing error: {str(e)}"}]


def get_gene_info(gene_symbol: str) -> dict:
    """
    Get basic gene information from NCBI Gene API.
    
    Args:
        gene_symbol: Gene symbol (e.g., 'APOE')
    
    Returns:
        dict: Gene information including Entrez ID
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "gene",
        "term": f"{gene_symbol}[Gene Name] AND Homo sapiens[Organism]",
        "retmode": "json",
        "retmax": 1
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
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
    """
    List available resources (knowledge graph endpoints, datasets, etc.)
    """
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
    """
    Read resource information
    """
    if uri == "pharmatlas://translator-kg":
        return json.dumps({
            "endpoint": "https://aragorn.renci.org/1.4/query",
            "description": "NCATS Translator Knowledge Graph",
            "supported_queries": ["gene-disease associations", "gene relationships"]
        }, indent=2)
    elif uri == "pharmatlas://ncbi-gene":
        return json.dumps({
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
            "description": "NCBI Gene Database",
            "supported_queries": ["gene ID lookup", "gene information"]
        }, indent=2)
    else:
        raise ValueError(f"Unknown resource: {uri}")


# ============================================================================
# MCP Tool Handlers
# ============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    List available tools for gene-disease analysis
    """
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
            description="Analyze a list of genes and find common disease associations",
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
                        "description": "Maximum number of genes to analyze (default: 5)",
                        "default": 5
                    }
                },
                "required": ["gene_symbols"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """
    Handle tool calls
    """
    if name == "find_gene_diseases":
        gene_symbol = arguments.get("gene_symbol", "").upper()
        
        # Get gene info first
        gene_info = get_gene_info(gene_symbol)
        
        if gene_info.get("status") != "found":
            return [TextContent(
                type="text",
                text=f"Could not find gene: {gene_symbol}"
            )]
        
        # Query Translator KG
        kg_result = query_translator_kg(gene_info["entrez_id"])
        diseases = extract_disease_associations(kg_result)
        
        # Format response
        result = {
            "gene": gene_symbol,
            "entrez_id": gene_info["entrez_id"],
            "disease_associations": diseases,
            "total_diseases_found": len(diseases)
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "get_gene_info":
        gene_symbol = arguments.get("gene_symbol", "").upper()
        gene_info = get_gene_info(gene_symbol)
        
        return [TextContent(
            type="text",
            text=json.dumps(gene_info, indent=2)
        )]
    
    elif name == "analyze_gene_list":
        gene_symbols = arguments.get("gene_symbols", [])
        limit = arguments.get("limit", 5)
        
        # Limit the number of genes to prevent timeout
        gene_symbols = [g.upper() for g in gene_symbols[:limit]]
        
        results = []
        disease_counts = {}
        
        for gene_symbol in gene_symbols:
            gene_info = get_gene_info(gene_symbol)
            
            if gene_info.get("status") == "found":
                kg_result = query_translator_kg(gene_info["entrez_id"])
                diseases = extract_disease_associations(kg_result)
                
                results.append({
                    "gene": gene_symbol,
                    "entrez_id": gene_info["entrez_id"],
                    "disease_count": len(diseases)
                })
                
                # Count disease occurrences
                for disease in diseases:
                    disease_name = disease.get("disease_name", "Unknown")
                    disease_counts[disease_name] = disease_counts.get(disease_name, 0) + 1
        
        # Find common diseases
        common_diseases = sorted(
            disease_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        summary = {
            "genes_analyzed": gene_symbols,
            "results": results,
            "common_diseases": [
                {"disease": d[0], "gene_count": d[1]}
                for d in common_diseases
            ]
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(summary, indent=2)
        )]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())