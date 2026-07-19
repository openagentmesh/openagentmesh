/** First sentence of a description, for compact table rows. */
export function firstSentence(text: string): string {
  const match = /^.*?[.!?](?=\s|$)/s.exec(text.trim());
  return match ? match[0] : text.trim();
}

export function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
