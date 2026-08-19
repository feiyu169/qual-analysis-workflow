/**
 * researchMode prompt 生成器
 * researchMode prompt generator
 * 負責將模板和參數組合成最終的 prompt
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";

/**
 * researchMode prompt 參數介面
 * researchMode prompt parameter interface
 */
export interface ResearchModePromptParams {
  topic: string;
  previousState: string;
  currentState: string;
  nextSteps: string;
  memoryDir: string;
}

/**
 * 獲取 researchMode 的完整 prompt
 * Get the complete researchMode prompt
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getResearchModePrompt(
  params: ResearchModePromptParams
): Promise<string> {
  // 處理之前的研究狀態
  // Process previous research state
  let previousStateContent = "";
  if (params.previousState && params.previousState.trim() !== "") {
    const previousStateTemplate = await loadPromptFromTemplate(
      "researchMode/previousState.md"
    );
    previousStateContent = generatePrompt(previousStateTemplate, {
      previousState: params.previousState,
    });
  } else {
    previousStateContent = "這是第一次進行此主題的研究，沒有之前的研究狀態。";
    // This is the first research on this topic, no previous research state.
  }

  // 載入主要模板
  // Load main template
  const indexTemplate = await loadPromptFromTemplate("researchMode/index.md");
  let prompt = generatePrompt(indexTemplate, {
    topic: params.topic,
    previousStateContent: previousStateContent,
    currentState: params.currentState,
    nextSteps: params.nextSteps,
    memoryDir: params.memoryDir,
    time: new Date().toLocaleString(),
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "RESEARCH_MODE");
}
