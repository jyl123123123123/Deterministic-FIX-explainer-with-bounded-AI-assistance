export interface SampleMessage {
  label: string;
  message: string;
}

export const SAMPLES: SampleMessage[] = [
  {
    label: 'Limit Buy (35=D)',
    message:
      '8=FIX.4.2|35=D|49=TRADER1|56=EXCHANGE|34=102|52=20260310-14:30:05|11=ORD-1001|55=AAPL|54=1|38=100|40=2|44=185.50|59=0|10=128|',
  },
  {
    label: 'Market Sell (35=D)',
    message:
      '8=FIX.4.2|35=D|49=HEDGEFUND|56=NASDAQ|34=7|52=20260310-15:41:12|11=ORD-2042|55=TSLA|54=2|38=250|40=1|59=3|10=072|',
  },
  {
    label: 'Execution Report (35=8)',
    message:
      '8=FIX.4.2|35=8|49=EXCHANGE|56=TRADER1|34=103|52=20260310-14:30:06|37=EX-9001|11=ORD-1001|17=E-50001|150=F|39=2|55=AAPL|54=1|38=100|32=100|31=185.50|14=100|6=185.50|60=20260310-14:30:06|10=231|',
  },
];
