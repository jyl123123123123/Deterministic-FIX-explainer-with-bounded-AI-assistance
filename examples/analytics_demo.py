"""Offline A -> B demo. No API key or network requests."""
from fix_explainer.analytics import TradingAnalytics
from fix_explainer.analytics_bridge import AnalyticsBridge
from fix_explainer.analytics_summary import TradingSummaryService
from fix_explainer.synthetic import generate_synthetic_messages
from fix_explainer.trading import TradingDataService


def main():
    analytics = TradingAnalytics()
    service = TradingDataService(event_observer=AnalyticsBridge(analytics))
    try:
        for message in generate_synthetic_messages(count=1500, seed=20261010):
            service.ingest(message)
        report = analytics.snapshot()
        print(TradingSummaryService().summarize(report)['summary'])
    finally:
        service.close()


if __name__ == '__main__':
    main()
