import { FIELD_NAMES, VALUE_MAPS, YN_MAP, YN_TAGS } from './dictionary';

export interface ParsedField {
  tag: number;
  name: string;
  rawValue: string;
  decoded: string;
}

export interface ParseResult {
  fields: ParsedField[];
  /** First occurrence of each tag, for quick lookups. */
  byTag: Record<number, ParsedField>;
  delimiterName: string;
}

const DELIMITERS = [
  { ch: '\u0001', name: 'SOH (0x01)' },
  { ch: '|', name: 'pipe (|)' },
  { ch: '^', name: 'caret (^)' },
];

export function parseFixMessage(raw: string): ParseResult {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error('Please paste a FIX message first.');
  }

  const delim = DELIMITERS.find((d) => trimmed.includes(d.ch));
  if (!delim) {
    throw new Error(
      'No supported delimiter found. Separate tag=value pairs with |, ^, or SOH (\\u0001).',
    );
  }

  const segments = trimmed
    .split(delim.ch)
    .map((s) => s.trim())
    .filter(Boolean);

  if (segments.length === 0) {
    throw new Error('No tag=value pairs found in the message.');
  }

  const fields: ParsedField[] = segments.map((seg, i) => {
    const eq = seg.indexOf('=');
    if (eq <= 0) {
      throw new Error(`Segment ${i + 1} ("${seg}") is not a valid tag=value pair.`);
    }
    const tagStr = seg.slice(0, eq);
    if (!/^\d+$/.test(tagStr)) {
      throw new Error(`Segment ${i + 1} has an invalid tag "${tagStr}" (tags must be numeric).`);
    }
    const tag = Number(tagStr);
    const rawValue = seg.slice(eq + 1);
    const map = VALUE_MAPS[tag] ?? (YN_TAGS.has(tag) ? YN_MAP : undefined);
    const decoded = map && map[rawValue] ? map[rawValue] : rawValue;
    return {
      tag,
      name: FIELD_NAMES[tag] ?? `Unknown (Tag ${tag})`,
      rawValue,
      decoded,
    };
  });

  const byTag: Record<number, ParsedField> = {};
  for (const f of fields) {
    if (!(f.tag in byTag)) byTag[f.tag] = f;
  }

  return { fields, byTag, delimiterName: delim.name };
}
