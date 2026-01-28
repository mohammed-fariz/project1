import sys
import json
from mcp.server import Server
from mcp.types import Tool, TextContent

# Create MCP server
server = Server("calculator")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="add",
            description="Add two numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name, arguments):
    if name == "add":
        result = arguments["a"] + arguments["b"]
        return [TextContent(type="text", text=str(result))]

# 🔴 VERY IMPORTANT
if __name__ == "__main__":
    server.run_stdio()
