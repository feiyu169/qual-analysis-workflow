import { z } from "zod";
import path from "path";
import { fileURLToPath } from "url";
import { getResearchModePrompt } from "../../prompts/index.js";
import { getMemoryDir } from "../../utils/paths.js";

// 研究模式工具
// Research mode tool
export const researchModeSchema = z.object({
  topic: z
    .string()
    .min(5, {
      message: "研究主題不能少於5個字符，請提供明確的研究主題",
      // Research topic cannot be less than 5 characters, please provide a clear research topic
    })
    .describe("要研究的程式編程主題內容，應該明確且具體"),
    // Programming topic content to be researched, should be clear and specific
  previousState: z
    .string()
    .optional()
    .default("")
    .describe(
      "之前的研究狀態和內容摘要，第一次執行時為空，後續會包含之前詳細且關鍵的研究成果，這將幫助後續的研究"
      // Previous research state and content summary, empty on first execution, subsequently contains previous detailed and key research results, this will help subsequent research
    ),
  currentState: z
    .string()
    .describe(
      "當前 Agent 主要該執行的內容，例如使用網路工具搜尋某些關鍵字或分析特定程式碼，研究完畢後請呼叫 research_mode 來記錄狀態並與之前的`previousState`整合，這將幫助你更好的保存與執行研究內容"
      // Main content that the current Agent should execute, such as using web tools to search for certain keywords or analyze specific code, after research is completed please call research_mode to record state and integrate with previous `previousState`, this will help you better save and execute research content
    ),
  nextSteps: z
    .string()
    .describe(
      "後續的計劃、步驟或研究方向，用來約束 Agent 不偏離主題或走錯方向，如果研究過程中發現需要調整研究方向，請更新此欄位"
      // Subsequent plans, steps or research directions, used to constrain Agent from deviating from topic or going in wrong direction, if need to adjust research direction during research process, please update this field
    ),
});

export async function researchMode({
  topic,
  previousState = "",
  currentState,
  nextSteps,
}: z.infer<typeof researchModeSchema>) {
  // 獲取基礎目錄路徑
  // Get base directory path
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const PROJECT_ROOT = path.resolve(__dirname, "../../..");
  const MEMORY_DIR = await getMemoryDir();

  // 使用prompt生成器獲取最終prompt
  // Use prompt generator to get final prompt
  const prompt = await getResearchModePrompt({
    topic,
    previousState,
    currentState,
    nextSteps,
    memoryDir: MEMORY_DIR,
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
