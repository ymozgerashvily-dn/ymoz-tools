#!/usr/bin/env python3
"""
Interactive script to generate and optionally run wbox test commands.

Usage:
    python wbox_test.py

Type 'help' at any prompt to get detailed information about that parameter.
"""

import subprocess
import sys

# Comprehensive help text for each parameter
PARAMETER_HELP = {
    'cheetah_handler': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHEETAH HANDLER                                                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether to use a remote cheetah handler for the test.              ║
║                                                                              ║
║  When ENABLED (yes):                                                         ║
║    - Adds CHEETAH_HANDLER=remote to the make command                         ║
║    - The test will use a remote cheetah handler instead of local processing  ║
║    - Useful for distributed testing or when testing remote handler behavior  ║
║                                                                              ║
║  When DISABLED (no):                                                         ║
║    - The parameter is excluded entirely from the command                     ║
║    - The test uses the default handler configuration                         ║
║                                                                              ║
║  Options: yes / no                                                           ║
║  Default: no (parameter excluded)                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'test_name': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  TEST NAME                                                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  The name of the wbox test to run.                                           ║
║                                                                              ║
║  This value is appended to 'test_wbox.' in the make command.                 ║
║                                                                              ║
║  Examples:                                                                   ║
║    - test_control_traffic     → make test_wbox.test_control_traffic          ║
║    - test_data_plane          → make test_wbox.test_data_plane               ║
║    - test_config_sync         → make test_wbox.test_config_sync              ║
║                                                                              ║
║  You can also specify a specific test method:                                ║
║    - TestClass.test_method    → make test_wbox.TestClass.test_method         ║
║                                                                              ║
║  This field is REQUIRED.                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'run_command': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  RUN COMMAND                                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether to execute the generated command or just display it.       ║
║                                                                              ║
║  When YES:                                                                   ║
║    - The generated command will be executed immediately via bash             ║
║    - Output will be shown in real-time                                       ║
║    - The script will exit with the command's return code                     ║
║                                                                              ║
║  When NO:                                                                    ║
║    - The command is only displayed (not executed)                            ║
║    - You can copy and paste it to run manually                               ║
║    - Useful for reviewing or modifying the command before running            ║
║                                                                              ║
║  Options: yes / no                                                           ║
║  Default: no (just show the command)                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'break_on_fail': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  BREAK ON FAIL (BP_ON_FAIL)                                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether the test should stop and enter debugger on failure.        ║
║                                                                              ║
║  When YES:                                                                   ║
║    - Adds BP_ON_FAIL=1 to the make command                                   ║
║    - Test execution stops at the first failure                               ║
║    - Enters an interactive debugger (pdb) for investigation                  ║
║    - Useful for debugging failing tests                                      ║
║                                                                              ║
║  When NO:                                                                    ║
║    - Adds BP_ON_FAIL=0 to the make command                                   ║
║    - Test continues running even after failures                              ║
║    - All test results are collected before exiting                           ║
║                                                                              ║
║  When EXCLUDE:                                                               ║
║    - Parameter is not added to the command                                   ║
║    - Uses the default behavior defined in the test framework                 ║
║                                                                              ║
║  Options: yes / no / exclude                                                 ║
║  Default: exclude (use framework default)                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'generate_config': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  GENERATE CONFIG (GENERATE_CONFIG)                                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether to regenerate configuration files before running tests.    ║
║                                                                              ║
║  When YES:                                                                   ║
║    - Adds GENERATE_CONFIG=1 to the make command                              ║
║    - Configuration files are regenerated from templates                      ║
║    - Ensures tests run with fresh, up-to-date configuration                  ║
║    - Takes longer but guarantees config consistency                          ║
║                                                                              ║
║  When NO:                                                                    ║
║    - Adds GENERATE_CONFIG=0 to the make command                              ║
║    - Uses existing configuration files (faster)                              ║
║    - Useful when config hasn't changed since last run                        ║
║                                                                              ║
║  When EXCLUDE:                                                               ║
║    - Parameter is not added to the command                                   ║
║    - Uses the default behavior defined in the Makefile                       ║
║                                                                              ║
║  Options: yes / no / exclude                                                 ║
║  Default: exclude (use Makefile default)                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'clear_logs': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  CLEAR LOGS                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether to clear existing log files before running the test.       ║
║                                                                              ║
║  When YES:                                                                   ║
║    - Adds 'clear_logs' command before the make command                       ║
║    - All existing log files in the test environment are deleted              ║
║    - Ensures logs only contain output from the current test run              ║
║    - Useful for clean test runs and easier log analysis                      ║
║                                                                              ║
║  When NO:                                                                    ║
║    - Existing logs are preserved                                             ║
║    - New log entries are appended to existing files                          ║
║    - Useful for tracking issues across multiple runs                         ║
║                                                                              ║
║  Options: yes / no                                                           ║
║  Default: no (preserve existing logs)                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
    'clear_containers': """
╔══════════════════════════════════════════════════════════════════════════════╗
║  CLEAR CONTAINERS                                                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Controls whether to stop and remove Docker containers before the test.      ║
║                                                                              ║
║  When YES:                                                                   ║
║    - Adds 'clear_containers' command before the make command                 ║
║    - All test-related Docker containers are stopped and removed              ║
║    - Ensures a clean container environment for the test                      ║
║    - Useful when containers are in an inconsistent state                     ║
║    - Takes longer as containers need to be recreated                         ║
║                                                                              ║
║  When NO:                                                                    ║
║    - Existing containers are preserved and reused                            ║
║    - Faster test startup if containers are already running                   ║
║    - May cause issues if containers are in a bad state                       ║
║                                                                              ║
║  Options: yes / no                                                           ║
║  Default: no (preserve existing containers)                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
""",
}


def show_help(param_name: str) -> None:
    """Display help text for a parameter."""
    if param_name in PARAMETER_HELP:
        print(PARAMETER_HELP[param_name])
    else:
        print(f"No help available for '{param_name}'")


def prompt_yes_no_exclude(question: str, help_key: str = None) -> str:
    """Prompt for yes/no/exclude answer. Type 'help' for more info."""
    while True:
        answer = input(f"{question} (yes/no/exclude) [exclude]: ").strip().lower()
        if answer in ('help', 'h', '?'):
            if help_key:
                show_help(help_key)
            else:
                print("No help available for this prompt.")
            continue
        if answer in ('', 'exclude', 'e', 'x'):
            return 'exclude'
        elif answer in ('yes', 'y'):
            return 'yes'
        elif answer in ('no', 'n'):
            return 'no'
        else:
            print("Please enter 'yes', 'no', 'exclude', or 'help'")


def prompt_yes_no(question: str, default: bool = False, help_key: str = None) -> bool:
    """Prompt for yes/no answer. Type 'help' for more info."""
    default_str = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{question} ({default_str}): ").strip().lower()
        if answer in ('help', 'h', '?'):
            if help_key:
                show_help(help_key)
            else:
                print("No help available for this prompt.")
            continue
        if answer == '':
            return default
        elif answer in ('yes', 'y'):
            return True
        elif answer in ('no', 'n'):
            return False
        else:
            print("Please enter 'yes', 'no', or 'help'")


def prompt_string(question: str, required: bool = True, help_key: str = None) -> str:
    """Prompt for a string input. Type 'help' for more info."""
    while True:
        answer = input(f"{question}: ").strip()
        if answer.lower() in ('help', 'h', '?'):
            if help_key:
                show_help(help_key)
            else:
                print("No help available for this prompt.")
            continue
        if answer or not required:
            return answer
        print("This field is required.")


def build_command(
    test_name: str,
    cheetah_handler: bool,
    break_on_fail: str,
    generate_config: str,
    clear_logs: bool,
    clear_containers: bool,
) -> str:
    """Build the shell command based on user inputs."""
    
    parts = ["cd ~/cheetah/src/tests"]
    
    # Add clear commands if requested
    if clear_containers:
        parts.append("clear_containers")
    
    if clear_logs:
        parts.append("clear_logs")
    
    # Build the make command
    make_cmd = f"make test_wbox.{test_name}"
    
    # Add optional parameters
    make_params = []
    
    if break_on_fail == 'yes':
        make_params.append("BP_ON_FAIL=1")
    elif break_on_fail == 'no':
        make_params.append("BP_ON_FAIL=0")
    # 'exclude' means don't add the parameter
    
    if cheetah_handler:
        make_params.append("CHEETAH_HANDLER=remote")
    # False means don't add the parameter at all
    
    if generate_config == 'yes':
        make_params.append("GENERATE_CONFIG=1")
    elif generate_config == 'no':
        make_params.append("GENERATE_CONFIG=0")
    # 'exclude' means don't add the parameter
    
    if make_params:
        make_cmd += " " + " ".join(make_params)
    
    parts.append(make_cmd)
    
    return " ; ".join(parts)


def main():
    print("=== WBox Test Command Generator ===")
    print("(Type 'help' at any prompt for detailed information)\n")
    
    # 1. Cheetah handler (simple yes/no - if yes, adds CHEETAH_HANDLER=remote)
    cheetah_handler = prompt_yes_no(
        "Include cheetah handler (remote)?", 
        default=False, 
        help_key='cheetah_handler'
    )
    
    # 2. Test name
    test_name = prompt_string(
        "Test name (e.g., test_control_traffic)",
        help_key='test_name'
    )
    
    # 3. Show or run
    run_command = prompt_yes_no(
        "Run the command? (no = just show)", 
        default=False,
        help_key='run_command'
    )
    
    # 4. Break on fail
    break_on_fail = prompt_yes_no_exclude(
        "Break on fail?",
        help_key='break_on_fail'
    )
    
    # 5. Generate config
    generate_config = prompt_yes_no_exclude(
        "Generate config?",
        help_key='generate_config'
    )
    
    # 6. Clear logs
    clear_logs = prompt_yes_no(
        "Clear logs?", 
        default=False,
        help_key='clear_logs'
    )
    
    # 7. Clear containers
    clear_containers = prompt_yes_no(
        "Clear containers?", 
        default=False,
        help_key='clear_containers'
    )
    
    # Build the command
    command = build_command(
        test_name=test_name,
        cheetah_handler=cheetah_handler,
        break_on_fail=break_on_fail,
        generate_config=generate_config,
        clear_logs=clear_logs,
        clear_containers=clear_containers,
    )
    
    print("\n" + "=" * 60)
    print("Generated command:")
    print("=" * 60)
    print(command)
    print("=" * 60 + "\n")
    
    if run_command:
        print("Running command...\n")
        # Use bash -c to run the compound command
        result = subprocess.run(['bash', '-c', command], text=True)
        sys.exit(result.returncode)
    else:
        print("Command not executed. Copy and paste to run manually.")


if __name__ == '__main__':
    main()

