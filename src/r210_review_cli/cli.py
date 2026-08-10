"""CLI entry point and argument parsing.

Usage:
    r210-review <command> [subcommand] [arguments] [options]

Commands:
    list    <entity_type>                     List artifacts/issues by type
    show    <unique_key>                      Show detailed record
    search  <entity_type> --name <pattern>    Search by name
    approve <unique_key> [--note <text>]      Set status to approved
    reject  <unique_key> [--note <text>]      Set status to rejected
    mark    <unique_key> <status> [--note]    Set any valid status
    resolve <issue_key> --resolution <text>   Resolve a review issue
    stats                                     Show database statistics
    generate <mode>                           Trigger generation

See: LLD-06 §4 (CLI Entry Point)
"""
