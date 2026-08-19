import { z } from "zod";
import { getInitProjectRulesPrompt } from "../../prompts/index.js";

// 定義schema
// Define schema
export const initProjectRulesSchema = z.object({});

/**
 * 初始化專案規範工具函數
 * Initialize project specification tool function
 * 提供建立規範文件的指導
 * Provide guidance for creating specification documents
 */
export async function initProjectRules() {
  try {
    // 從生成器獲取提示詞
    // Get prompt from generator
    const promptContent = await getInitProjectRulesPrompt();

    // 返回成功響應
    // Return success response
    return {
      content: [
        {
          type: "text" as const,
          text: promptContent,
        },
      ],
    };
  } catch (error) {
    // 錯誤處理
    // Error handling
    const errorMessage = error instanceof Error ? error.message : "未知錯誤";
    // Unknown error
    return {
      content: [
        {
          type: "text" as const,
          text: `初始化專案規範時發生錯誤: ${errorMessage}`,
          // Error occurred during project specification initialization: ${errorMessage}
        },
      ],
    };
  }
}
