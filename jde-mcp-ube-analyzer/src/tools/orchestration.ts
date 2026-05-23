import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  JdeCallOrchestrationSchema,
  type JdeCallOrchestrationInput,
} from "../schemas/tools.js";
import { callOrchestration } from "../services/ais-client.js";
import { CHARACTER_LIMIT } from "../constants.js";

export function registerOrchestrationTool(server: McpServer): void {
  server.registerTool(
    "jde_call_orchestration",
    {
      title: "Call JDE Orchestration",
      description: `Invoke a named JDE Orchestration via the AIS REST API.

Use this for WRITE/TRANSACTIONAL operations — creating sales orders, updating records, or running multi-step business processes that have been pre-built as JDE Orchestrations in the Orchestrator Studio.

⚠️ This tool can MODIFY DATA in JDE. Use with caution and only when the user explicitly requests a create/update/delete operation.

For READ operations, prefer jde_query_table or the curated inquiry tools instead.

Args:
  - orchestrationName (string): Name of the orchestration (as defined in Orchestrator Studio)
  - inputs (object): Key-value map of input parameters expected by the orchestration

Returns:
  JSON response from the orchestration — structure depends on the specific orchestration's output definition.

Examples:
  - orchestrationName: "CreateSalesOrder"
    inputs: { "Customer": "4242", "ItemNumber": "ABC123", "Quantity": "10", "BranchPlant": "M30" }
  - orchestrationName: "UpdateOrderStatus"
    inputs: { "OrderNumber": "12345", "NewStatus": "580" }`,
      inputSchema: JdeCallOrchestrationSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async (params: JdeCallOrchestrationInput) => {
      try {
        const result = await callOrchestration(
          params.orchestrationName,
          params.inputs
        );

        let text = JSON.stringify(result, null, 2);
        if (text.length > CHARACTER_LIMIT) {
          text = text.slice(0, CHARACTER_LIMIT) + "\n\n... [TRUNCATED]";
        }

        return {
          content: [{ type: "text" as const, text }],
        };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          isError: true,
          content: [{
            type: "text" as const,
            text: `Error calling orchestration "${params.orchestrationName}": ${msg}. ` +
              `Verify the orchestration name and required input parameters.`,
          }],
        };
      }
    }
  );
}
