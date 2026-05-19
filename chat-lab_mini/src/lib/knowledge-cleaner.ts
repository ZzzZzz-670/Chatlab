const INTERNAL_TITLE_MAP: Record<string, string> = {
  "后台想判断": "判断方向",
  "不要问": "避免这样问",
  "改问": "建议这样问",
  "家长标签": "常见说法",
  "不直接采信": "需要进一步了解",
};

const REMOVE_TITLES = ["后台想判断", "不要问", "改问", "家长标签"];

function cleanTableRow(line: string): string {
  const stripped = line.trim();
  if (!stripped.startsWith("|") || !stripped.endsWith("|")) return stripped;
  const cells = stripped
    .slice(1, -1)
    .split("|")
    .map((cell) => cell.trim())
    .filter((cell) => cell && cell !== "---" && !/^[-:\s]+$/.test(cell));
  if (!cells.length) return "";
  if (REMOVE_TITLES.some((title) => cells[0].includes(title))) return "";
  if (cells.length >= 3) return `关于${cells[0]}：不要问「${cells[1]}」，建议问「${cells[2]}」`;
  return cells.join("；");
}

export function cleanChunk(text: string): string {
  const cleanedLines: string[] = [];
  for (let line of text.split("\n")) {
    line = line.trim();
    if (!line || /^[|\-:\s]+$/.test(line)) continue;
    line = line.replace(/^#{1,6}\s*/, "");
    if (/^[一二三四五六七八九十百千零〇]+[、.．]\s*/.test(line)) continue;
    if (/^(\d+[.．、]|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s*/.test(line)) continue;
    if (line.startsWith("是否")) continue;
    if (line.startsWith("|") && line.endsWith("|")) {
      const cleaned = cleanTableRow(line);
      if (cleaned) cleanedLines.push(cleaned);
      continue;
    }
    for (const [oldText, replacement] of Object.entries(INTERNAL_TITLE_MAP)) {
      line = line.replaceAll(oldText, replacement);
    }
    cleanedLines.push(line);
  }
  return cleanedLines.join("\n").replace(/\n{3,}/g, "\n\n");
}
