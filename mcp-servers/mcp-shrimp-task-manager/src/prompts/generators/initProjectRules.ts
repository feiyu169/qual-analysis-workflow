/**
 * initProjectRules prompt 生成器
 * initProjectRules prompt generator
 * 負責將模板和參數組合成最終的 prompt
 * Responsible for combining templates and parameters into the final prompt
 */

import { loadPrompt, loadPromptFromTemplate } from "../loader.js";
/**
 * initProjectRules prompt 參數介面
 * initProjectRules prompt parameters interface
 */
export interface InitProjectRulesPromptParams {
  // 目前沒有額外參數，未來可按需擴展
  // Currently no additional parameters, can be expanded as needed in the future
}

/**
 * 獲取 initProjectRules 的完整 prompt
 * Get the complete prompt for initProjectRules
 * @param params prompt 參數（可選）
 * @param params prompt parameters (optional)
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getInitProjectRulesPrompt(
  params?: InitProjectRulesPromptParams
): Promise<string> {
  const indexTemplate = await loadPromptFromTemplate(
    "initProjectRules/index.md"
  );

  // 載入可能的自定義 prompt (通過環境變數覆蓋或追加)
  // Load possible custom prompt (override or append via environment variables)
  return loadPrompt(indexTemplate, "INIT_PROJECT_RULES");
}
