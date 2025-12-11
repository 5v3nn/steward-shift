"""
Main entry point for shift scheduling application.
"""

import sys
import argparse

from .config import ConfigLoader, ConfigurationError, InvalidDateFormatError
from .optimizer import ShiftOptimizer
from .reporter import ScheduleReporter


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="steward-shift",
        description="Optimize employee shift schedules using linear programming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full report with all details
  steward-shift config/schedule.yaml

  # Minimal output
  steward-shift config/schedule.yaml --quiet

  # Export to CSV
  steward-shift config/schedule.yaml --export-csv output.csv
        """,
    )

    parser.add_argument("config", type=str, help="Path to YAML configuration file")
    parser.add_argument("--export-csv", type=str, help="Export schedule to CSV file")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output (only show summary)",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        print(f"Loading configuration from: {args.config}")
        loader = ConfigLoader(args.config)
        config = loader.load()

        print("✓ Configuration loaded successfully")
        print(loader.get_summary())
        print()

        # Run optimization
        print("Running optimization...")
        optimizer = ShiftOptimizer(config)
        result = optimizer.optimize()
        print("✓ Optimization complete")
        print()

        # Generate report
        reporter = ScheduleReporter(result)

        print(f"Status: {result.status}")
        if result.is_optimal:
            print(f"Total shifts assigned: {result.total_shifts_required}")

        reporter.print_report(args.quiet)

        # Export to CSV if requested
        if args.export_csv:
            reporter.export_to_csv(args.export_csv)

        # Exit with appropriate code
        sys.exit(0 if result.is_optimal else 1)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    except InvalidDateFormatError as e:
        print(f"Date Format Error: {e}", file=sys.stderr)
        print(
            "\n Tip: Use ISO 8601 format (YYYY-MM-DD) for all dates.", file=sys.stderr
        )
        print("   Example: 2026-01-15", file=sys.stderr)
        sys.exit(1)

    except ConfigurationError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"Unexpected Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
