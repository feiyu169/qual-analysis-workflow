/**
 * prompt 載入器
 * prompt loader
 * 提供從環境變數載入自定義 prompt 的功能
 * Provides functionality to load custom prompts from environment variables
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { getDataDir } from "../utils/paths.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function processEnvString(input: string | undefined): string {
  if (!input) return "";

  return input
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\r/g, "\r");
}

/**
 * 載入 prompt，支援環境變數自定義
 * Load prompt with environment variable customization support
 * @param basePrompt 基本 prompt 內容
 * @param basePrompt Basic prompt content
 * @param promptKey prompt 的鍵名，用於生成環境變數名稱
 * @param promptKey Prompt key name, used to generate environment variable names
 * @returns 最終的 prompt 內容
 * @returns Final prompt content
 */
export function loadPrompt(basePrompt: string, promptKey: string): string {
  // 轉換為大寫，作為環境變數的一部分
  // Convert to uppercase as part of the environment variable
  const envKey = promptKey.toUpperCase();

  // 檢查是否有替換模式的環境變數
  // Check if there is a replacement mode environment variable
  const overrideEnvVar = `MCP_PROMPT_${envKey}`;
  if (process.env[overrideEnvVar]) {
    // 使用環境變數完全替換原始 prompt
    // Use environment variable to completely replace original prompt
    return processEnvString(process.env[overrideEnvVar]);
  }

  // 檢查是否有追加模式的環境變數
  // Check if there is an append mode environment variable
  const appendEnvVar = `MCP_PROMPT_${envKey}_APPEND`;
  if (process.env[appendEnvVar]) {
    // 將環境變數內容追加到原始 prompt 後
    // Append environment variable content to the original prompt
    return `${basePrompt}\n\n${processEnvString(process.env[appendEnvVar])}`;
  }

  // 如果沒有自定義，則使用原始 prompt
  // If no customization, use the original prompt
  return basePrompt;
}

/**
 * 生成包含動態參數的 prompt
 * Generate prompt with dynamic parameters
 * @param promptTemplate prompt 模板
 * @param promptTemplate prompt template
 * @param params 動態參數
 * @param params dynamic parameters
 * @returns 填充參數後的 prompt
 * @returns Prompt with parameters filled in
 */
export function generatePrompt(
  promptTemplate: string,
  params: Record<string, any> = {}
): string {
  // 使用簡單的模板替換方法，將 {paramName} 替換為對應的參數值
  // Use simple template replacement method to replace {paramName} with corresponding parameter values
  let result = promptTemplate;

  Object.entries(params).forEach(([key, value]) => {
    // 如果值為 undefined 或 null，使用空字串替換
    // If value is undefined or null, replace with empty string
    const replacementValue =
      value !== undefined && value !== null ? String(value) : "";

    // 使用正則表達式替換所有匹配的佔位符
    // Use regular expression to replace all matching placeholders
    const placeholder = new RegExp(`\\{${key}\\}`, "g");
    result = result.replace(placeholder, replacementValue);
  });

  return result;
}

/**
 * 從模板載入 prompt
 * Load prompt from template
 * @param templatePath 相對於模板集根目錄的模板路徑 (e.g., 'chat/basic.md')
 * @param templatePath Template path relative to template set root directory (e.g., 'chat/basic.md')
 * @returns 模板內容
 * @returns Template content
 * @throws Error 如果找不到模板文件
 * @throws Error if template file is not found
 */
export async function loadPromptFromTemplate(
  templatePath: string
): Promise<string> {
  const templateSetName = process.env.TEMPLATES_USE || "en";
  const dataDir = await getDataDir();
  const builtInTemplatesBaseDir = __dirname;

  let finalPath = "";
  const checkedPaths: string[] = []; // 用於更詳細的錯誤報告
  // Used for more detailed error reporting

  // 1. 檢查 DATA_DIR 中的自定義路徑
  // 1. Check custom paths in DATA_DIR
  // path.resolve 可以處理 templateSetName 是絕對路徑的情況
  // path.resolve can handle cases where templateSetName is an absolute path
  const customFilePath = path.resolve(dataDir, templateSetName, templatePath);
  checkedPaths.push(`Custom: ${customFilePath}`);
  if (fs.existsSync(customFilePath)) {
    finalPath = customFilePath;
  }

  // 2. 如果未找到自定義路徑，檢查特定的內建模板目錄
  // 2. If custom path not found, check specific built-in template directory
  if (!finalPath) {
    // 假設 templateSetName 對於內建模板是 'en', 'zh' 等
    // Assume templateSetName for built-in templates is 'en', 'zh', etc.
    const specificBuiltInFilePath = path.join(
      builtInTemplatesBaseDir,
      `templates_${templateSetName}`,
      templatePath
    );
    checkedPaths.push(`Specific Built-in: ${specificBuiltInFilePath}`);
    if (fs.existsSync(specificBuiltInFilePath)) {
      finalPath = specificBuiltInFilePath;
    }
  }

  // 3. 如果特定的內建模板也未找到，且不是 'en' (避免重複檢查)
  // 3. If specific built-in template is also not found and not 'en' (avoid duplicate checking)
  if (!finalPath && templateSetName !== "en") {
    const defaultBuiltInFilePath = path.join(
      builtInTemplatesBaseDir,
      "templates_en",
      templatePath
    );
    checkedPaths.push(`Default Built-in ('en'): ${defaultBuiltInFilePath}`);
    if (fs.existsSync(defaultBuiltInFilePath)) {
      finalPath = defaultBuiltInFilePath;
    }
  }

  // 4. 如果所有路徑都找不到模板，拋出錯誤
  // 4. If template is not found in all paths, throw error
  if (!finalPath) {
    throw new Error(
      `Template file not found: '${templatePath}' in template set '${templateSetName}'. Checked paths:\n - ${checkedPaths.join(
        "\n - "
      )}`
    );
  }

  // 5. 讀取找到的文件
  // 5. Read the found file
  return fs.readFileSync(finalPath, "utf-8");
}
