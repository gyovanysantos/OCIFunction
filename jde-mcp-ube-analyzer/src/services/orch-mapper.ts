import { readFile } from "fs/promises";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ──────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────

interface OrchFieldMapping {
  [toolField: string]: string;   // toolField → orchestration input field name
}

interface OrchConfig {
  orchestrationName: string;
  _description?: string;
  inputMapping: OrchFieldMapping;
  outputMapping: OrchFieldMapping;
}

interface OrchConfigFile {
  _comment?: string;
  createSalesOrder: OrchConfig;
  updateSalesOrderLine: OrchConfig;
  addSalesOrderLines: OrchConfig;
  cancelSalesOrder: OrchConfig;
}

let config: OrchConfigFile | null = null;

// ──────────────────────────────────────────────────────────────
// Load
// ──────────────────────────────────────────────────────────────

async function loadConfig(): Promise<OrchConfigFile> {
  if (config) return config;
  const configPath = join(__dirname, "..", "data", "orchestrations.json");
  const raw = await readFile(configPath, "utf-8");
  config = JSON.parse(raw) as OrchConfigFile;
  return config;
}

// ──────────────────────────────────────────────────────────────
// Mapping helpers
// ──────────────────────────────────────────────────────────────

/**
 * Maps tool-level inputs to orchestration-level inputs using the
 * field mapping in orchestrations.json.
 *
 * Handles flat fields and array fields (lines[].xxx → mapped array).
 */
function mapInputs(
  toolInputs: Record<string, unknown>,
  mapping: OrchFieldMapping
): Record<string, unknown> {
  const orchInputs: Record<string, unknown> = {};

  // Separate flat and array-pattern mappings
  const flatMappings: Array<[string, string]> = [];
  const arrayFieldMap = new Map<string, Map<string, string>>(); // arrayName → { subField → orchField }
  let arrayOrchKey = "";

  for (const [toolField, orchField] of Object.entries(mapping)) {
    const arrayMatch = toolField.match(/^(\w+)\[\]\.(\w+)$/);
    if (arrayMatch) {
      const [, arrayName, subField] = arrayMatch;
      if (!arrayFieldMap.has(arrayName)) {
        arrayFieldMap.set(arrayName, new Map());
      }
      arrayFieldMap.get(arrayName)!.set(subField, orchField);
    } else {
      flatMappings.push([toolField, orchField]);
    }
  }

  // Map flat fields
  for (const [toolField, orchField] of flatMappings) {
    const value = toolInputs[toolField];
    if (value !== undefined && value !== null) {
      // Check if this field maps an array — if so, handle via array mapping
      if (arrayFieldMap.has(toolField)) {
        arrayOrchKey = orchField;
        // Will be filled below
      } else {
        orchInputs[orchField] = value;
      }
    }
  }

  // Map array fields (e.g. lines → OrderLines)
  for (const [arrayName, subMappings] of arrayFieldMap.entries()) {
    const sourceArray = toolInputs[arrayName];
    if (!Array.isArray(sourceArray)) continue;

    // Find the orchestration key for the array itself
    const orchArrayKey = mapping[arrayName] ?? arrayName;

    const mappedArray = sourceArray.map((item: Record<string, unknown>) => {
      const mappedItem: Record<string, unknown> = {};
      for (const [subField, orchField] of subMappings.entries()) {
        if (item[subField] !== undefined && item[subField] !== null) {
          mappedItem[orchField] = item[subField];
        }
      }
      return mappedItem;
    });

    orchInputs[orchArrayKey] = mappedArray;
  }

  return orchInputs;
}

// ──────────────────────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────────────────────

export type OrchOperation =
  | "createSalesOrder"
  | "updateSalesOrderLine"
  | "addSalesOrderLines"
  | "cancelSalesOrder";

export async function getOrchestrationName(
  operation: OrchOperation
): Promise<string> {
  const cfg = await loadConfig();
  return cfg[operation].orchestrationName;
}

export async function buildOrchestrationPayload(
  operation: OrchOperation,
  toolInputs: Record<string, unknown>
): Promise<{ orchestrationName: string; inputs: Record<string, unknown> }> {
  const cfg = await loadConfig();
  const orchCfg = cfg[operation];

  return {
    orchestrationName: orchCfg.orchestrationName,
    inputs: mapInputs(toolInputs, orchCfg.inputMapping),
  };
}
