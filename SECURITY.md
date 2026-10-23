# Security

Realign checks declared files and finite contracts. It is not a sandbox and not a guarantee of general semantic correctness. Policy effects are data: it does not run tools, migrations or project commands.

Use a trusted installation of the harness, review your contracts, and keep the baseline under version control. A digest detects internal changes, but anyone who can replace the file can also recompute it. Locks are cooperative; replacements are atomic per file, with no durable multi-file transaction. An adversarial writer running as the same user, and path races, are outside these guarantees.

The hook checks the Git index and can be skipped; complement it with CI. Evidence files omit data values, but they contain file names and identifiers that may be sensitive. Review them before sharing.

## Reporting a vulnerability

Use **Security -> Report a vulnerability** if GitHub shows that private channel on the repository. If it is not available, open only a private-contact request with no exploit details or sensitive data. Do not publish secrets, credentials, private files, or a reproduction containing them in issues or comments.

Include the version, the affected scope and a minimal reproduction using fictitious data through the private channel that is available. No response time is promised, and only the latest version is covered.
