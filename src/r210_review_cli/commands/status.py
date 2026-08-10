"""Status change commands: approve, reject, mark.

Delegates to ReviewToolBridge.set_review_status() which calls
the MCP server's handler directly with caller="review".

See: LLD-06 §6.2 (Status Commands)
"""
