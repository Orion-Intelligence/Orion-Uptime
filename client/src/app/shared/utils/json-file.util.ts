import Json5 from 'json5';

export interface ParsedJsonFile {
  value: unknown;
  repaired: boolean;
}

export function parseJsonFile(contents: string): ParsedJsonFile {
  const normalized = stripCodeFence(contents.replace(/^\uFEFF/, '').trim());
  if (!normalized) {
    throw new Error('The selected file is empty. Add a monitor configuration in JSON format.');
  }

  try {
    return { value: JSON.parse(normalized) as unknown, repaired: false };
  }
  catch {
    try {
      const value = Json5.parse(normalized) as unknown;
      assertJsonCompatible(value);
      return { value, repaired: true };
    }
    catch (error) {
      const detail = error instanceof Error ? error.message.replace(/^JSON5:\s*/i, '') : '';
      throw new Error(`The file contains JSON syntax that could not be repaired${detail ? ` (${detail})` : ''}. Use valid JSON or JSON5 syntax.`);
    }
  }
}

function stripCodeFence(contents: string): string {
  const fenced = contents.match(/^```(?:json|json5)?\s*([\s\S]*?)\s*```$/i);
  return fenced?.[1]?.trim() ?? contents;
}

function assertJsonCompatible(value: unknown): void {
  if (typeof value === 'number' && !Number.isFinite(value)) {
    throw new Error('Non-finite numbers are not valid monitor configuration values');
  }
  if (Array.isArray(value)) {
    value.forEach(assertJsonCompatible);
    return;
  }
  if (value && typeof value === 'object') {
    Object.values(value).forEach(assertJsonCompatible);
  }
}
