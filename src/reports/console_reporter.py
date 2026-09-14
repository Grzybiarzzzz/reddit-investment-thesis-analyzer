# src/reports/console_reporter.py


class ConsoleReporter:
    def format_discoveries(self, discoveries: list[dict]) -> str:
        if not discoveries:
            return "No new stock discoveries today."

        lines = ["=== New Stock Discoveries ==="]
        for d in discoveries:
            lines.append(
                f"  {d['ticker']:6s} | Price: ${d['price']:.2f} | "
                f"Mentions: {d['mentions']} | Avg Score: {d['avg_score']:.1f}"
            )
        return "\n".join(lines)

    def format_checkpoints(self, updates: list[dict]) -> str:
        if not updates:
            return "No checkpoint updates today."

        lines = ["=== Checkpoint Updates ==="]
        for u in updates:
            lines.append(
                f"  {u['ticker']:6s} | {u['checkpoint']}-day checkpoint | "
                f"Price: ${u['price']:.2f}"
            )
        return "\n".join(lines)

    def format_performance(self, stocks: list[dict], checkpoint: int) -> str:
        if not stocks:
            return f"No completed {checkpoint}-day tracks yet."

        price_field = f"price_{checkpoint}d"
        spy_field = f"spy_price_{checkpoint}d"

        lines = [f"=== {checkpoint}-Day Performance ==="]
        for s in stocks:
            if s.get(price_field) is None or s.get("discovery_price") is None:
                continue

            stock_return = ((s[price_field] - s["discovery_price"]) / s["discovery_price"]) * 100
            spy_return = 0
            if s.get("spy_price_discovery") and s.get(spy_field):
                spy_return = ((s[spy_field] - s["spy_price_discovery"]) / s["spy_price_discovery"]) * 100

            alpha = stock_return - spy_return
            direction = "+" if alpha >= 0 else ""

            lines.append(
                f"  {s['ticker']:6s} | Return: {stock_return:+.1f}% | "
                f"SPY: {spy_return:+.1f}% | Alpha: {direction}{alpha:.1f}%"
            )
        return "\n".join(lines)

    def print_report(self, discoveries: list[dict], checkpoint_updates: list[dict],
                     completed_stocks: list[dict]):
        print()
        print("=" * 50)
        print("  Reddit Stock Analyzer - Daily Report")
        print("=" * 50)
        print()
        print(self.format_discoveries(discoveries))
        print()
        print(self.format_checkpoints(checkpoint_updates))
        print()
        for cp in [7, 14, 30, 90]:
            relevant = [s for s in completed_stocks if s.get(f"price_{cp}d") is not None]
            if relevant:
                print(self.format_performance(relevant, cp))
                print()
