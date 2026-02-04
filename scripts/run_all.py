import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from pdfgen.render import build_sample_data, render_pdf


def run_sample():
    data = build_sample_data()
    render_pdf(data, output_path=ROOT / "output.pdf")


def run_demo():
    from scripts import demo_report

    demo_report.main()


def run_stress():
    from scripts import stress_harness

    stress_harness.main()


def main():
    parser = argparse.ArgumentParser(description="Run PDF generation checks.")
    parser.add_argument("--sample", action="store_true", help="Render sample output.pdf")
    parser.add_argument("--demo", action="store_true", help="Render demo_output.pdf")
    parser.add_argument("--stress", action="store_true", help="Run stress harness")
    args = parser.parse_args()

    # Default: run sample + demo
    run_any = args.sample or args.demo or args.stress
    if not run_any:
        args.sample = True
        args.demo = True

    if args.sample:
        run_sample()
    if args.demo:
        run_demo()
    if args.stress:
        run_stress()


if __name__ == "__main__":
    main()
