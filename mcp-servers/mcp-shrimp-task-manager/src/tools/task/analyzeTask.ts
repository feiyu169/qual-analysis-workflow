import { z } from "zod";
import { getAnalyzeTaskPrompt } from "../../prompts/index.js";

// 分析問題工具
// Task analysis tool
export const analyzeTaskSchema = z.object({
  summary: z
    .string()
    .min(10, {
      message: "任務摘要不能少於10個字符，請提供更詳細的描述以確保任務目標明確",
      // Task summary must be at least 10 characters long, please provide a more detailed description to ensure clear task objectives
    })
    .describe(
      "結構化的任務摘要，包含任務目標、範圍與關鍵技術挑戰，最少10個字符"
      // Structured task summary including task objectives, scope and key technical challenges, minimum 10 characters
    ),
  initialConcept: z
    .string()
    .min(50, {
      message:
        "初步解答構想不能少於50個字符，請提供更詳細的內容確保技術方案清晰",
        // Initial solution concept must be at least 50 characters long, please provide more detailed content to ensure clear technical solution
    })
    .describe(
      "最少50個字符的初步解答構想，包含技術方案、架構設計和實施策略，如果需要提供程式碼請使用 pseudocode 格式且僅提供高級邏輯流程和關鍵步驟避免完整代碼"
      // Initial solution concept of at least 50 characters, including technical solution, architectural design and implementation strategy. If code is needed, use pseudocode format providing only high-level logic flow and key steps, avoiding complete code
    ),
  previousAnalysis: z
    .string()
    .optional()
    .describe("前次迭代的分析結果，用於持續改進方案（僅在重新分析時需提供）"),
    // Previous iteration analysis results, used for continuous solution improvement (only required when re-analyzing)
});

export async function analyzeTask({
  summary,
  initialConcept,
  previousAnalysis,
}: z.infer<typeof analyzeTaskSchema>) {
  // 使用prompt生成器獲取最終prompt
  // Use prompt generator to get the final prompt
  const prompt = await getAnalyzeTaskPrompt({
    summary,
    initialConcept,
    previousAnalysis,
  });

  return {
    content: [
      {
        type: "text" as const,
        text: prompt,
      },
    ],
  };
}
