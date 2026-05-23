# Azure Agent Deployment Plan — v2.0

**Status**: Ready to deploy  
**Date**: 2026-04-11  
**Target**: Azure Container Apps (`jde-mcp-env`, East US)

---

## Pre-requisites (Already Done)

| Resource | Status | Details |
|----------|--------|---------|
| MCP Server | ✅ Deployed | `jde-mcp-integrity` on Container Apps, healthy |
| ACR | ✅ Ready | `acrjdemcppo.azurecr.io` |
| Container Apps Env | ✅ Exists | `jde-mcp-env` (East US) |
| Foundry Project | ✅ Ready | `gsantos-hackaton26`, model `gpt-4o` |
| Agent Code | ✅ Tested | All 3 containers start and run locally |

---

## Architecture

```
┌─ Azure Container Apps (jde-mcp-env) ──────────────────────────────┐
│                                                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   │
│  │ Extractor    │   │ Analyzer     │   │ jde-mcp-integrity    │   │
│  │ Port: 8088   │   │ Port: 8088   │──>│ Port: 3000           │   │
│  │ 0.5 CPU/1GB  │   │ 0.25 CPU/0.5 │   │ (Already deployed)   │   │
│  │ Internal     │   │ Internal     │   │ External             │   │
│  └──────┬───────┘   └──────────────┘   └──────────────────────┘   │
│         │                                                          │
└─────────┼──────────────────────────────────────────────────────────┘
          │ HTTPS
          ▼
   OCI Object Storage
   (OBJECTSTORAGE bucket)
```

---

## Step 1: Build & Push Images to ACR

> ⚠️ **Do NOT use `az acr build`** — it produces broken images. Use local Docker only.

```powershell
# Login to ACR
az acr login --name acrjdemcppo

# Build Extractor
docker build -t acrjdemcppo.azurecr.io/jde-extractor:v1 ./agents/extractor
docker push acrjdemcppo.azurecr.io/jde-extractor:v1

# Build Analyzer
docker build -t acrjdemcppo.azurecr.io/jde-analyzer:v1 ./agents/analyzer
docker push acrjdemcppo.azurecr.io/jde-analyzer:v1
```

---

## Step 2: Create Managed Identity

Both agents need to authenticate to Azure AI Foundry via `DefaultAzureCredential`.

```powershell
# Create identity
az identity create -g rg-hackathon-2603 -n jde-agents-identity

# Get IDs
$IDENTITY_ID = az identity show -g rg-hackathon-2603 -n jde-agents-identity --query id -o tsv
$IDENTITY_PRINCIPAL = az identity show -g rg-hackathon-2603 -n jde-agents-identity --query principalId -o tsv

# Assign Cognitive Services role on Foundry resource
az role assignment create `
  --role "Cognitive Services OpenAI Contributor" `
  --assignee-object-id $IDENTITY_PRINCIPAL `
  --assignee-principal-type ServicePrincipal `
  --scope "/subscriptions/74528fbf-d0fa-4d72-b3ef-dee45c2a8293/resourceGroups/rg-hackathon-2603/providers/Microsoft.CognitiveServices/accounts/gsantos-hackaton26-resource"
```

---

## Step 3: Handle OCI Credentials (Extractor Only)

The ExtractorAgent needs OCI API credentials to download PDFs. Options:

### Option A: Environment Variables (Simplest)
Set OCI config values directly as env vars. Requires modifying `agent.py` to use `oci.config.from_raw()` instead of `oci.config.from_file()`.

### Option B: Secret Volume (Current Code — No Code Change)
Mount OCI config as a Container Apps secret volume:

```powershell
# Create Key Vault (if not exists)
az keyvault create -n kv-jde-hackathon -g rg-hackathon-2603 -l eastus

# Store OCI config file
az keyvault secret set --vault-name kv-jde-hackathon --name oci-config --file "$HOME/.oci/config"

# Store OCI private key
az keyvault secret set --vault-name kv-jde-hackathon --name oci-api-key --file "$HOME/.oci/cl-oci-lab/oci_api_key.pem"
```

---

## Step 4: Deploy ExtractorAgent

```powershell
az containerapp create `
  --name jde-extractor `
  --resource-group rg-hackathon-2603 `
  --environment jde-mcp-env `
  --image acrjdemcppo.azurecr.io/jde-extractor:v1 `
  --target-port 8088 `
  --ingress internal `
  --registry-server acrjdemcppo.azurecr.io `
  --user-assigned $IDENTITY_ID `
  --cpu 0.5 --memory 1.0Gi `
  --min-replicas 0 --max-replicas 3 `
  --env-vars `
    FOUNDRY_PROJECT_ENDPOINT="https://gsantos-hackaton26-resource.services.ai.azure.com/api/projects/gsantos-hackaton26" `
    FOUNDRY_MODEL_DEPLOYMENT_NAME="gpt-4o" `
    OCI_BUCKET_NAME="OBJECTSTORAGE" `
    OCI_NAMESPACE="idxoqn0ijjyv"
```

---

## Step 5: Deploy AnalyzerAgent

```powershell
az containerapp create `
  --name jde-analyzer `
  --resource-group rg-hackathon-2603 `
  --environment jde-mcp-env `
  --image acrjdemcppo.azurecr.io/jde-analyzer:v1 `
  --target-port 8088 `
  --ingress internal `
  --registry-server acrjdemcppo.azurecr.io `
  --user-assigned $IDENTITY_ID `
  --cpu 0.25 --memory 0.5Gi `
  --min-replicas 0 --max-replicas 3 `
  --env-vars `
    FOUNDRY_PROJECT_ENDPOINT="https://gsantos-hackaton26-resource.services.ai.azure.com/api/projects/gsantos-hackaton26" `
    FOUNDRY_MODEL_DEPLOYMENT_NAME="gpt-4o" `
    MCP_SERVER_URL="https://jde-mcp-integrity.bluedesert-fb732cac.eastus.azurecontainerapps.io/mcp"
```

> **Note**: If jde-mcp-integrity is on the same Container Apps environment, you could use internal DNS: `http://jde-mcp-integrity:3000/mcp`

---

## Step 6: Verify

```powershell
# Check running status
az containerapp show -g rg-hackathon-2603 -n jde-extractor --query "properties.runningStatus" -o tsv
az containerapp show -g rg-hackathon-2603 -n jde-analyzer --query "properties.runningStatus" -o tsv

# Check logs
az containerapp logs show -g rg-hackathon-2603 -n jde-extractor --follow
az containerapp logs show -g rg-hackathon-2603 -n jde-analyzer --follow
```

---

## Environment Variables Summary

| Variable | Extractor | Analyzer |
|----------|:---------:|:--------:|
| `FOUNDRY_PROJECT_ENDPOINT` | ✅ | ✅ |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | ✅ | ✅ |
| `OCI_BUCKET_NAME` | ✅ | — |
| `OCI_NAMESPACE` | ✅ | — |
| `MCP_SERVER_URL` | — | ✅ |
| Azure Auth (Managed Identity) | ✅ | ✅ |
| OCI Auth (config file) | ✅ | — |

---

## Resource Sizing

| Service | CPU | Memory | Min Replicas | Max Replicas |
|---------|-----|--------|:------------:|:------------:|
| MCP Server | 0.25 | 0.5Gi | 0 | 3 |
| Extractor | 0.5 | 1.0Gi | 0 | 3 |
| Analyzer | 0.25 | 0.5Gi | 0 | 3 |

All services scale to 0 when idle to minimize costs.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| OCI credentials in Container Apps | Use Key Vault secret volume mount |
| MCP cold start (scale-to-0) | First request may be slow; consider min-replicas=1 for MCP |
| Foundry auth failure | Verify managed identity role assignment before deploying |
| `az acr build` crash | Always use local `docker push` |
