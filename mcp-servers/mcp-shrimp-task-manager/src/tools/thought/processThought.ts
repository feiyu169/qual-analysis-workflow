import { z } from "zod";
import {
  getProcessThoughtPrompt,
  ProcessThoughtPromptParams,
} from "../../prompts/generators/processThought.js";

/**
 * processThought工具的參數結構
 * Parameter structure for the processThought tool
 */
export const processThoughtSchema = z.object({
  thought: z
    .string()
    .min(1, {
      message: "思維內容不能為空，請提供有效的思考內容",
      // message: "Thought content cannot be empty, please provide valid thinking content",
    })
    .describe("思維內容"),
    // .describe("Thought content")
  thought_number: z
    .number()
    .int()
    .positive({
      message: "思維編號必須是正整數",
      // message: "Thought number must be a positive integer",
    })
    .describe("當前思維編號"),
    // .describe("Current thought number")
  total_thoughts: z
    .number()
    .int()
    .positive({
      message: "總思維數必須是正整數",
      // message: "Total thoughts must be a positive integer",
    })
    .describe("預計總思維數量，如果需要更多的思考可以隨時變更"),
    // .describe("Expected total number of thoughts, can be changed anytime if more thinking is needed")
  next_thought_needed: z.boolean().describe("是否需要下一步思維"),
  // next_thought_needed: z.boolean().describe("Whether next thought is needed")
  stage: z
    .string()
    .min(1, {
      message: "思維階段不能為空，請提供有效的思考階段",
      // message: "Thinking stage cannot be empty, please provide a valid thinking stage",
    })
    .describe(
      "Thinking stage. Available stages include: Problem Definition, Information Gathering, Research, Analysis, Synthesis, Conclusion, Critical Questioning, and Planning."
    ),
  tags: z.array(z.string()).optional().describe("思維標籤，是一個陣列字串"),
  // tags: z.array(z.string()).optional().describe("Thought tags, an array of strings")
  axioms_used: z
    .array(z.string())
    .optional()
    .describe("使用的公理，是一個陣列字串"),
    // .describe("Axioms used, an array of strings")
  assumptions_challenged: z
    .array(z.string())
    .optional()
    .describe("挑戰的假設，是一個陣列字串"),
    // .describe("Assumptions challenged, an array of strings")
});

/**
 * 處理單一思維並返回格式化輸出
 * Process a single thought and return formatted output
 */
export async function processThought(
  params: z.infer<typeof processThoughtSchema>
) {
  try {
    // 將參數轉換為規範的ThoughtData格式
    // Convert parameters to standard ThoughtData format
    const thoughtData: ProcessThoughtPromptParams = {
      thought: params.thought,
      thoughtNumber: params.thought_number,
      totalThoughts: params.total_thoughts,
      nextThoughtNeeded: params.next_thought_needed,
      stage: params.stage,
      tags: params.tags || [],
      axioms_used: params.axioms_used || [],
      assumptions_challenged: params.assumptions_challenged || [],
    };

    // 確保思維編號不超過總思維數
    // Ensure thought number does not exceed total thoughts
    if (thoughtData.thoughtNumber > thoughtData.totalThoughts) {
      // 自動調整總思維數量
      // Automatically adjust total thoughts count
      thoughtData.totalThoughts = thoughtData.thoughtNumber;
    }

    // 格式化思維輸出
    // Format thought output
    const formattedThought = await getProcessThoughtPrompt(thoughtData);

    // 返回成功響應
    // Return success response
    return {
      content: [
        {
          type: "text" as const,
          text: formattedThought,
        },
      ],
    };
  } catch (error) {
    // 捕獲並處理所有未預期的錯誤
    // Catch and handle all unexpected errors
    const errorMessage = error instanceof Error ? error.message : "未知錯誤";
    // const errorMessage = error instanceof Error ? error.message : "Unknown error";
    return {
      content: [
        {
          type: "text" as const,
          text: `處理思維時發生錯誤: ${errorMessage}`,
          // text: `Error occurred while processing thought: ${errorMessage}`,
        },
      ],
    };
  }
}
