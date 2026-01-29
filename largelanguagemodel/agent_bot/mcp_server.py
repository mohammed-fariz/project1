# from mcp.server.fastmcp import FastMCP
# import time
# import json

# # -------------------------------------------------
# # Create MCP server (tool execution layer)
# # -------------------------------------------------
# mcp = FastMCP("agent-bot-mcp")

# # -------------------------------------------------
# # Tools (pure functions, no LLM logic)
# # -------------------------------------------------
# @mcp.tool()
# def health_check() -> str:
#     """Check whether MCP server is alive"""
#     return "MCP server is running"

# @mcp.tool()
# def get_current_time() -> str:
#     """Return current server time"""
#     return time.strftime("%Y-%m-%d %H:%M:%S")

# @mcp.tool()
# def echo(message: str) -> str:
#     """Echo back the given message"""
#     return f"Echo: {message}"

# @mcp.tool()
# def add_numbers(a: int, b: int) -> int:
#     """Add two numbers"""
#     return a + b

# @mcp.tool()
# def fetch_user_data(user_id: int) -> str:
#     """Fetch mock user data"""
#     users = {
#         1: {"name": "Alice", "role": "admin"},
#         2: {"name": "Bob", "role": "user"},
#     }
#     return json.dumps(users.get(user_id, "User not found"))

# # -------------------------------------------------
# # Run MCP server (stdio – blocking, expected)
# # -------------------------------------------------
# if __name__ == "__main__":
#     print("MCP server started (stdio mode). Waiting for client...")
#     mcp.run()
from mcp.server.fastmcp import FastMCP
import time

# --------------------------------
# MCP SERVER
# --------------------------------
mcp = FastMCP("math-and-utils-mcp")

# --------------------------------
# TOOLS
# --------------------------------
@mcp.tool()
def health_check() -> str:
    """Check MCP server status"""
    return "MCP server is alive"

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def get_current_time() -> str:
    """Get current server time"""
    return time.strftime("%Y-%m-%d %H:%M:%S")

# --------------------------------
# RUN (STDIO – REQUIRED)
# --------------------------------
if __name__ == "__main__":
    mcp.run()
