function normalizeText(value: string) {
  return value
    .toLowerCase()
    .replace(/[`*_#$]/g, "")
    .replace(/[^\w.%]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function similarity(a: string, b: string) {
  const aWords = new Set(normalizeText(a).split(" ").filter(Boolean));
  const bWords = new Set(normalizeText(b).split(" ").filter(Boolean));
  if (aWords.size === 0 || bWords.size === 0) return 0;
  let overlap = 0;
  for (const word of aWords) {
    if (bWords.has(word)) overlap += 1;
  }
  return overlap / Math.min(aWords.size, bWords.size);
}

export function cleanChatText(value: string) {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/\$([^$]+)\$/g, "$1")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[*]\s+/gm, "- ")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

export function displayChatAnswer(answer: string, summary: string) {
  let text = cleanChatText(answer);
  const summaryText = cleanChatText(summary);

  const recommendedActionsStart = text.search(/\n\s*recommended actions\s*:/i);
  if (recommendedActionsStart >= 0) {
    text = text.slice(0, recommendedActionsStart).trim();
  }

  const paragraphs = text.split(/\n\s*\n/);
  const firstParagraph = paragraphs[0]?.trim() ?? "";
  if (firstParagraph && similarity(firstParagraph, summaryText) >= 0.8) {
    return paragraphs.slice(1).join("\n\n").trim();
  }

  const firstSentence = text.match(/^(.+?[.!?])(\s|\n|$)/)?.[1];
  if (firstSentence && similarity(firstSentence, summaryText) >= 0.8) {
    return text.slice(firstSentence.length).trim();
  }

  return text;
}
