#!/usr/bin/env python3
"""
Test runner script for BoolStreet backend.
Provides convenient commands for running different types of tests.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """
    Run a command and handle errors gracefully.
    
    Args:
        cmd: Command to run as a list
        description: Description of what the command does
    
    Returns:
        bool: True if command succeeded, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"❌ Command not found: {' '.join(cmd)}")
        return False


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(
        description="BoolStreet Backend Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests
  python run_tests.py --unit             # Run only unit tests
  python run_tests.py --api              # Run only API tests
  python run_tests.py --coverage         # Run tests with coverage report
  python run_tests.py --file test_auth   # Run specific test file
  python run_tests.py --verbose          # Run with verbose output
        """
    )
    
    # Test selection options
    parser.add_argument('--all', action='store_true', 
                       help='Run all tests (default)')
    parser.add_argument('--unit', action='store_true',
                       help='Run only unit tests')
    parser.add_argument('--integration', action='store_true',
                       help='Run only integration tests')
    parser.add_argument('--api', action='store_true',
                       help='Run only API tests')
    parser.add_argument('--auth', action='store_true',
                       help='Run only authentication tests')
    parser.add_argument('--database', action='store_true',
                       help='Run only database tests')
    parser.add_argument('--file', type=str,
                       help='Run specific test file (e.g., test_auth)')
    
    # Output options
    parser.add_argument('--coverage', action='store_true',
                       help='Generate coverage report')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--quiet', action='store_true',
                       help='Quiet output')
    parser.add_argument('--no-cov', action='store_true',
                       help='Disable coverage reporting')
    
    # Performance options
    parser.add_argument('--parallel', action='store_true',
                       help='Run tests in parallel')
    parser.add_argument('--fast', action='store_true',
                       help='Skip slow tests')
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not Path('tests').exists():
        print("❌ Error: tests directory not found. Please run from the backend directory.")
        sys.exit(1)
    
    # Build pytest command
    cmd = ['python', '-m', 'pytest']
    
    # Add test selection
    if args.file:
        cmd.append(f'tests/test_{args.file}.py')
    elif args.unit:
        cmd.extend(['-m', 'unit'])
    elif args.integration:
        cmd.extend(['-m', 'integration'])
    elif args.api:
        cmd.extend(['-m', 'api'])
    elif args.auth:
        cmd.extend(['-m', 'auth'])
    elif args.database:
        cmd.extend(['-m', 'database'])
    else:
        # Run all tests by default
        cmd.append('tests/')
    
    # Add output options
    if args.verbose:
        cmd.append('-v')
    elif args.quiet:
        cmd.append('-q')
    
    # Add coverage options
    if args.coverage or not args.no_cov:
        cmd.extend(['--cov=.', '--cov-report=html', '--cov-report=term-missing'])
    
    # Add performance options
    if args.parallel:
        cmd.extend(['-n', 'auto'])  # Requires pytest-xdist
    
    if args.fast:
        cmd.extend(['-m', 'not slow'])
    
    # Run the tests
    success = run_command(cmd, "Running tests")
    
    if success:
        print(f"\n🎉 All tests completed successfully!")
        
        if args.coverage or not args.no_cov:
            print(f"\n📊 Coverage report generated:")
            print(f"   - HTML: htmlcov/index.html")
            print(f"   - Terminal output above")
    else:
        print(f"\n💥 Some tests failed. Check the output above for details.")
        sys.exit(1)


if __name__ == '__main__':
    main() 