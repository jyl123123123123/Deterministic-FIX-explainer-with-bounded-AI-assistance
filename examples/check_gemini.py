"""One opt-in live aggregate check. May incur provider charges; never saves a key."""
import getpass
import os
import sys
import warnings

from fix_explainer.analytics import TradingAnalytics
from fix_explainer.analytics_summary import GeminiTradingSummaryProvider, TradingSummaryService


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run in an interactive terminal. No request was made.')
    print('This makes at most one real Gemini request and may incur provider charges.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            key = os.environ.get('GEMINI_API_KEY') or getpass.getpass('Gemini API key (hidden): ').strip()
            model = os.environ.get('GEMINI_MODEL') or input('Gemini model ID: ').strip()
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
            raise SystemExit('Cancelled or secure input unavailable. No request was made.') from None
    if not key or not model:
        raise SystemExit('Key and model are required. No request was made.')
    provider = GeminiTradingSummaryProvider(api_key=key, model=model)
    result = TradingSummaryService(provider, enabled=True, max_calls=1).summarize(
        TradingAnalytics().snapshot(), use_ai=True)
    print('Provider:', result['provider'])
    print('Fallback reason:', result['fallback_reason'])
    if result['provider'] != 'gemini':
        raise SystemExit(1)
    print('Live bounded aggregate response validated successfully. No credentials were saved.')


if __name__ == '__main__':
    main()
