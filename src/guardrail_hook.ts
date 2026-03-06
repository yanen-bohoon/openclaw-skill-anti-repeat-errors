/**
 * Anti-Repeat-Errors Skill - Before Tool Call Hook
 *
 * TypeScript hook handler that bridges to the Python guardrail module.
 */

import type { PluginApi, BeforeToolCallContext, HookResult } from "@openclaw/plugin-sdk";
import { spawn } from "child_process";
import * as path from "path";

/**
 * Guardrail result from Python
 */
interface GuardrailResult {
  allowed: boolean;
  modified: boolean;
  tool_name: string;
  original_params: Record<string, any>;
  result_params: Record<string, any>;
  rule_id?: string;
  rule_name?: string;
  action?: string;
  message?: string;
  duration_ms: number;
}

/**
 * Plugin configuration
 */
interface PluginConfig {
  enabled?: boolean;
  guardrailEnabled?: boolean;
  guardrailTimeout?: number;
  guardrailRulesDir?: string;
  rulesDir?: string;
  logLevel?: "debug" | "info" | "warn" | "error";
}

/**
 * Register the before_tool_call hook
 */
export function registerBeforeToolCallHook(api: PluginApi, config: PluginConfig): void {
  const logger = api.logger;

  // Check if guardrail is enabled
  if (config.guardrailEnabled === false) {
    logger.info("Guardrail disabled by config");
    return;
  }

  api.registerHook(
    "before_tool_call",
    async (ctx: BeforeToolCallContext): Promise<HookResult> => {
      const startTime = Date.now();

      try {
        // Build context
        const guardrailContext = {
          session_key: ctx.sessionKey,
          phase: getCurrentPhase(ctx),
          task_type: inferTaskType(ctx),
          message_content: getLastUserMessage(ctx),
        };

        // Call Python guardrail
        const result = await callPythonGuardrail(
          ctx.toolName,
          ctx.toolParams,
          guardrailContext,
          config,
          logger
        );

        // Handle result
        if (!result.allowed) {
          // Blocked
          logger.warn(
            `Tool call blocked by rule ${result.rule_id}: ${result.message}`
          );
          
          // Record metric
          recordGuardrailMetric(result, "blocked", api);
          
          // Return error to agent
          return {
            continue: false,
            error: {
              code: "GUARDRAIL_BLOCKED",
              message: result.message || `Blocked by guardrail rule: ${result.rule_name}`,
              details: {
                rule_id: result.rule_id,
                rule_name: result.rule_name,
              },
            },
          };
        }

        if (result.modified) {
          // Rewritten
          logger.info(
            `Tool call rewritten by rule ${result.rule_id}: ${result.message}`
          );
          
          // Update params
          ctx.toolParams = result.result_params;
          
          // Record metric
          recordGuardrailMetric(result, "rewritten", api);
        }

        if (result.action === "warn" && result.message) {
          // Warning
          logger.warn(`Guardrail warning: ${result.message}`);
          
          // Add warning to context (agent can see it)
          ctx.prependContext = (ctx.prependContext || "") + 
            `\n\n<!-- guardrail-warning -->\n${result.message}\n<!-- /guardrail-warning -->\n`;
          
          recordGuardrailMetric(result, "warned", api);
        }

        if (result.rule_id && result.action === "log") {
          // Logged only
          logger.info(`Guardrail log: rule ${result.rule_id} matched`);
          recordGuardrailMetric(result, "logged", api);
        }

        // Allow to continue
        return { continue: true };

      } catch (error) {
        logger.error(`Guardrail processing failed: ${error}`);
        // Don't block on error
        return { continue: true };
      }
    },
    {
      name: "anti-repeat-errors.before_tool_call",
      description: "Intercepts tool calls and applies guardrail rules",
      priority: 100, // High priority
    }
  );

  logger.info("Registered before_tool_call hook");
}

/**
 * Call Python guardrail CLI
 */
async function callPythonGuardrail(
  toolName: string,
  toolParams: Record<string, any>,
  context: Record<string, any>,
  config: PluginConfig,
  logger: any
): Promise<GuardrailResult> {
  const scriptPath = path.join(__dirname, "guardrail_cli.py");
  const timeout = config.guardrailTimeout || 500; // 500ms default

  // Build args
  const args = [
    scriptPath,
    "--tool-name", toolName,
    "--tool-params", JSON.stringify(toolParams),
    "--context", JSON.stringify(context),
  ];

  // Add rules dir if specified
  const rulesDir = config.guardrailRulesDir || config.rulesDir;
  if (rulesDir) {
    args.push("--rules-dir", rulesDir);
  }

  return new Promise((resolve, reject) => {
    let resolved = false;

    const proc = spawn("python3", args);

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
      if (config.logLevel === "debug") {
        logger.debug(`[Python] ${data.toString().trim()}`);
      }
    });

    proc.on("close", (code) => {
      if (resolved) return;
      resolved = true;

      if (code === 0) {
        try {
          const result = JSON.parse(stdout.trim()) as GuardrailResult;
          resolve(result);
        } catch (e) {
          logger.error(`Failed to parse guardrail output: ${stdout}`);
          resolve({
            allowed: true,
            modified: false,
            tool_name: toolName,
            original_params: toolParams,
            result_params: toolParams,
            message: `Parse error: ${e}`,
            duration_ms: 0,
          });
        }
      } else {
        resolve({
          allowed: true, // Don't block on error
          modified: false,
          tool_name: toolName,
          original_params: toolParams,
          result_params: toolParams,
          message: `Guardrail exit code ${code}: ${stderr}`,
          duration_ms: 0,
        });
      }
    });

    proc.on("error", (error) => {
      if (resolved) return;
      resolved = true;
      resolve({
        allowed: true,
        modified: false,
        tool_name: toolName,
        original_params: toolParams,
        result_params: toolParams,
        message: `Spawn error: ${error}`,
        duration_ms: 0,
      });
    });

    // Timeout
    setTimeout(() => {
      if (resolved) return;
      resolved = true;
      proc.kill();
      logger.warn(`Guardrail timeout after ${timeout}ms`);
      resolve({
        allowed: true, // Don't block on timeout
        modified: false,
        tool_name: toolName,
        original_params: toolParams,
        result_params: toolParams,
        message: "Timeout",
        duration_ms: timeout,
      });
    }, timeout);
  });
}

/**
 * Record guardrail metric
 */
function recordGuardrailMetric(
  result: GuardrailResult,
  status: string,
  api: PluginApi
): void {
  if (api.metrics) {
    api.metrics.record("anti_repeat_errors_guardrail", {
      tool_name: result.tool_name,
      rule_id: result.rule_id,
      action: result.action,
      status,
      duration_ms: result.duration_ms,
    });
  }
}

/**
 * Get current phase from context
 */
function getCurrentPhase(ctx: any): number | undefined {
  if (ctx.projectState?.phase) return ctx.projectState.phase;
  const phaseEnv = process.env.ANTI_REPEAT_ERRORS_PHASE;
  if (phaseEnv) {
    const phase = parseInt(phaseEnv, 10);
    if (!isNaN(phase)) return phase;
  }
  return undefined;
}

/**
 * Infer task type from context
 */
function inferTaskType(ctx: any): string | undefined {
  if (ctx.taskType) return ctx.taskType;
  const tools = ctx.sessionHistory?.recentTools || [];
  if (tools.includes("write") || tools.includes("edit")) return "coding";
  if (tools.includes("exec")) return "shell";
  return undefined;
}

/**
 * Get last user message
 */
function getLastUserMessage(ctx: any): string | undefined {
  const messages = ctx.messages || [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return messages[i].content;
  }
  return undefined;
}

export default registerBeforeToolCallHook;