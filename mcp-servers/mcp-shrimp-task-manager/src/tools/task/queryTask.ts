import { z } from "zod";
import { searchTasksWithCommand } from "../../models/taskModel.js";
import { getQueryTaskPrompt } from "../../prompts/index.js";

// 查詢任務工具
// Query task tool
export const queryTaskSchema = z.object({
  query: z
    .string()
    .min(1, {
      message: "查詢內容不能為空，請提供任務ID或搜尋關鍵字",
      // Query content cannot be empty, please provide task ID or search keywords
    })
    .describe("搜尋查詢文字，可以是任務ID或多個關鍵字（空格分隔）"),
    // Search query text, can be task ID or multiple keywords (space-separated)
  isId: z
    .boolean()
    .optional()
    .default(false)
    .describe("指定是否為ID查詢模式，默認為否（關鍵字模式）"),
    // Specify whether it is ID query mode, default is false (keyword mode)
  page: z
    .number()
    .int()
    .positive()
    .optional()
    .default(1)
    .describe("分頁頁碼，默認為第1頁"),
    // Page number, default is page 1
  pageSize: z
    .number()
    .int()
    .positive()
    .min(1)
    .max(20)
    .optional()
    .default(5)
    .describe("每頁顯示的任務數量，默認為5筆，最大20筆"),
    // Number of tasks displayed per page, default is 5, maximum is 20
});

export async function queryTask({
  query,
  isId = false,
  page = 1,
  pageSize = 3,
}: z.infer<typeof queryTaskSchema>) {
  try {
    // 使用系統指令搜尋函數
    // Use system command search function
    const results = await searchTasksWithCommand(query, isId, page, pageSize);

    // 使用prompt生成器獲取最終prompt
    // Use prompt generator to get the final prompt
    const prompt = await getQueryTaskPrompt({
      query,
      isId,
      tasks: results.tasks,
      totalTasks: results.pagination.totalResults,
      page: results.pagination.currentPage,
      pageSize,
      totalPages: results.pagination.totalPages,
    });

    return {
      content: [
        {
          type: "text" as const,
          text: prompt,
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text" as const,
          text: `## 系統錯誤\n\n查詢任務時發生錯誤: ${
          // ## System Error\n\nAn error occurred while querying tasks: ${
            error instanceof Error ? error.message : String(error)
          }`,
        },
      ],
      isError: true,
    };
  }
}
