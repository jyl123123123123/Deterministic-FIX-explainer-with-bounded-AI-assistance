// Builds complete, integrity-valid FIX 4.4 NewOrderSingle messages that pass
// the backend's schema subset (tests/fixtures/fix_orchestra_subset.xml) with
// zero validation findings. The field set mirrors tests/fixtures/new_order_single.fix.

const SOH = '\u0001';

export interface OrderParams {
  symbol: string;
  side: '1' | '2'; // 1=Buy, 2=Sell
  quantity: string;
  orderType: '1' | '2'; // 1=Market, 2=Limit (note: subset schema only defines 2=Limit)
  price?: string;
}

/**
 * Returns the wire message with SOH delimiters.
 * BodyLength = bytes from the SOH after tag 9's value up to and including the
 * SOH before tag 10. CheckSum = sum of all bytes before "10=" mod 256.
 * All content is ASCII, so string length / charCodeAt equal byte counts.
 */
export function buildNewOrderSingle(params: OrderParams): string {
  const clOrdId = `ORD-${Date.now()}`;
  const body: Array<[number, string]> = [
    [35, 'D'],
    [49, 'FIXINSIGHT'],
    [56, 'EXCHANGE'],
    [11, clOrdId],
    [55, params.symbol],
    [54, params.side],
    [38, params.quantity],
    [40, params.orderType],
  ];
  if (params.orderType === '2' && params.price) {
    body.push([44, params.price]);
  }
  const bodyStr = body.map(([tag, value]) => `${tag}=${value}`).join(SOH) + SOH;
  const head = `8=FIX.4.4${SOH}9=${bodyStr.length}${SOH}`;
  const withoutChecksum = head + bodyStr;
  let sum = 0;
  for (let i = 0; i < withoutChecksum.length; i++) {
    sum += withoutChecksum.charCodeAt(i);
  }
  return `${withoutChecksum}10=${String(sum % 256).padStart(3, '0')}${SOH}`;
}

/** Human-readable rendering: SOH shown as pipe. */
export function toDisplay(message: string): string {
  return message.split(SOH).join('|');
}
