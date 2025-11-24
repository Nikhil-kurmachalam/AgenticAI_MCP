# AI MCP Prototype – Week 1 & 2

## Overview
This project implements an AI-driven MCP (Multi-Modal Computational Prototype) to analyze gene expression, map genes to diseases, and explore drug associations using the NCATS Knowledge Graph.

---

## Week 1: Gene Expression Analysis
- Loaded and cleaned **GSE33000** Alzheimer’s dataset (1,248 samples, 39,280 genes)  
- Calculated variance and selected **top 200 genes**  
- Mapped gene symbols to **NCBI Entrez IDs**  
- Prepared dataset for downstream knowledge graph queries  

**Code:** `high_variance_genes_with_entrez_ids.ipynb`

---

## Week 2: Disease & Drug Associations
- Queried **NCATS Translator BioThings Explorer** using Entrez IDs  
- Extracted disease associations for top genes  
- Implemented initial drug association retrieval  

**Code:** `KG_Query.py`, `KnowledgeGraphTools.py`

---

## Challenges
- Mapping gene symbols to unique IDs  
- Understanding knowledge graph structure  
- Configuring MCP server and APIs  
- Extracting drug associations reliably  

---

## Next Steps
- Update Notion pages for Week 1 & 2  
- Add full drug integration  
- Set up MCP server with sample AI query  
- Recalculate top variance genes using **standardization**  
- Push updated code to GitHub  

---

## Folder Structure
```
data/                 # Gene data with Entrez IDs
mcp_server/           # MCP server scripts
notebooks/            # Variance analysis notebooks
README.md
requirements.txt