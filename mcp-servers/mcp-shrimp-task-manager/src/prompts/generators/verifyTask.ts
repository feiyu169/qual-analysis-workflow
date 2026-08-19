/**
 * verifyTask prompt 生成器
 * verifyTask prompt generator
 * 負責將模板和參數組合成最終的 prompt
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";
import { Task } from "../../types/index.js";

/**
 * verifyTask prompt 參數介面
 * verifyTask prompt parameters interface
 */
export interface VerifyTaskPromptParams {
  task: Task;
  score: number;
  summary: string;
}

/**
 * 提取摘要內容
 * Extract summary content
 * @param content 原始內容
 * @param content Original content
 * @param maxLength 最大長度
 * @param maxLength Maximum length
 * @returns 提取的摘要
 * @returns Extracted summary
 */
function extractSummary(
  content: string | undefined,
  maxLength: number
): string {
  if (!content) return "";

  if (content.length <= maxLength) {
    return content;
  }

  // 簡單的摘要提取：截取前 maxLength 個字符並添加省略號
  // Simple summary extraction: truncate to first maxLength characters and add ellipsis
  return content.substring(0, maxLength) + "...";
}

/**
 * 獲取 verifyTask 的完整 prompt
 * Get the complete prompt for verifyTask
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns Generated prompt
 */
export async function getVerifyTaskPrompt(
  params: VerifyTaskPromptParams
): Promise<string> {
  const { task, score, summary } = params;
  if (score < 80) {
    const noPassTemplate = await loadPromptFromTemplate("verifyTask/noPass.md");
    const prompt = generatePrompt(noPassTemplate, {
      name: task.name,
      id: task.id,
      summary,
    });
    return prompt;
  }
  const indexTemplate = await loadPromptFromTemplate("verifyTask/index.md");
  const prompt = generatePrompt(indexTemplate, {
    name: task.name,
    id: task.id,
    description: task.description,
    notes: task.notes || "no notes",
    verificationCriteria:
      task.verificationCriteria || "no verification criteria",
    implementationGuideSummary:
      extractSummary(task.implementationGuide, 200) ||
      "no implementation guide",
    analysisResult:
      extractSummary(task.analysisResult, 300) || "no analysis result",
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "VERIFY_TASK");
}
