import type { ParseResult, ParsedField } from './parser';

export interface Explanation {
  paragraph: string;
  evidence: string[];
  disclaimers: string[];
}

const SIDE_WORDS: Record<string, string> = {
  '1': 'buy',
  '2': 'sell',
  '5': 'sell short',
  '6': 'sell short (exempt)',
};

function fmtPrice(value: string): string {
  return value.startsWith('$') ? value : `$${value}`;
}

export function buildExplanation(result: ParseResult): Explanation {
  const get = (tag: number): ParsedField | undefined => result.byTag[tag];
  const evidence: string[] = [];
  const disclaimers: string[] = [];

  const note = (field: ParsedField | undefined, extra?: string) => {
    if (field) {
      evidence.push(
        `Tag ${field.tag} (${field.name}) = ${field.rawValue}${extra ? ` — ${extra}` : ''}`,
      );
    }
  };

  const msgType = get(35);
  const symbol = get(55);
  const side = get(54);
  const qty = get(38);
  const ordType = get(40);
  const price = get(44);
  const tif = get(59);

  let paragraph: string;

  if (msgType?.rawValue === 'D') {
    // New Order Single — a request.
    const sideWord = side ? (SIDE_WORDS[side.rawValue] ?? 'trade') : 'trade';
    const qtyText = qty ? `${qty.rawValue} shares of ` : '';
    const symbolText = symbol ? symbol.rawValue : 'an unspecified instrument';
    let orderDesc: string;
    if (ordType?.rawValue === '2') {
      orderDesc = `a limit order${price ? ` priced at ${fmtPrice(price.rawValue)}` : ''}`;
    } else if (ordType?.rawValue === '1') {
      orderDesc = 'a market order';
    } else if (ordType) {
      orderDesc = `a ${ordType.decoded.toLowerCase()} order`;
    } else {
      orderDesc = 'an order';
    }
    paragraph = `This message describes a request to ${sideWord} ${qtyText}${symbolText} using ${orderDesc}.`;
    if (tif) {
      paragraph += ` The time-in-force is ${tif.decoded}.`;
    }
    note(msgType, 'New Order Single');
    note(side, side?.decoded);
    note(qty, 'order quantity');
    note(symbol);
    note(ordType, ordType?.decoded);
    note(price, 'limit price');
    note(tif, tif?.decoded);
    disclaimers.push(
      'This message does not prove that the order was accepted or executed; it only records the intent expressed by the sender.',
    );
  } else if (msgType?.rawValue === '8') {
    // Execution Report — a report about what happened.
    const execType = get(150);
    const ordStatus = get(39);
    const cumQty = get(14);
    const lastQty = get(32);
    const lastPx = get(31);
    const avgPx = get(6);
    const sideWord = side ? (SIDE_WORDS[side.rawValue] ?? 'traded') : 'traded';

    let statusPhrase: string;
    if (execType?.rawValue === 'F' || execType?.rawValue === '2') {
      statusPhrase = `a fill was executed${lastQty ? ` for ${lastQty.rawValue} shares` : ''}${lastPx ? ` at ${fmtPrice(lastPx.rawValue)}` : ''}`;
    } else if (execType?.rawValue === '1') {
      statusPhrase = `a partial fill was executed${lastQty ? ` for ${lastQty.rawValue} shares` : ''}${lastPx ? ` at ${fmtPrice(lastPx.rawValue)}` : ''}`;
    } else if (execType) {
      statusPhrase = `the order event "${execType.decoded}" was reported`;
    } else {
      statusPhrase = 'an order event was reported';
    }
    paragraph = `This message is an Execution Report indicating that ${statusPhrase} on the ${sideWord} order${symbol ? ` for ${symbol.rawValue}` : ''}.`;
    if (cumQty) {
      paragraph += ` Cumulative filled quantity is ${cumQty.rawValue}${avgPx ? ` at an average price of ${fmtPrice(avgPx.rawValue)}` : ''}.`;
    }
    if (ordStatus) {
      paragraph += ` The order status is now "${ordStatus.decoded}".`;
    }
    note(msgType, 'Execution Report');
    note(execType, execType?.decoded);
    note(ordStatus, ordStatus?.decoded);
    note(side, side?.decoded);
    note(symbol);
    note(qty, 'original order quantity');
    note(lastQty, 'last executed quantity');
    note(lastPx, 'last executed price');
    note(cumQty, 'cumulative filled quantity');
    note(avgPx, 'average fill price');
    disclaimers.push(
      'An Execution Report reflects what the sender reported; it does not by itself prove clearing or settlement of the trade.',
    );
  } else if (msgType) {
    paragraph = `This is a FIX ${msgType.decoded} message${symbol ? ` referencing ${symbol.rawValue}` : ''}.`;
    note(msgType, msgType.decoded);
    note(symbol);
    if (['0', 'A', '5', '1', '2', '4'].includes(msgType.rawValue)) {
      disclaimers.push(
        'This is a session-level administrative message; it carries no order or trade information.',
      );
    }
  } else {
    paragraph = 'This FIX message has no MsgType (Tag 35), so its purpose cannot be determined.';
    disclaimers.push(
      'A FIX message without Tag 35 (MsgType) is not a well-formed message.',
    );
  }

  disclaimers.push(
    'Field values are decoded exactly as presented; checksum (Tag 10) and body length (Tag 9) are not verified, and this analysis is not investment advice.',
  );

  return { paragraph, evidence, disclaimers };
}
