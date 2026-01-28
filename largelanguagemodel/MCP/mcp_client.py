import asyncio
from fastmcp.client import Client

async def main():
    # Connect to MCP HTTP server
    client = Client(url="http://127.0.0.1:8000")

    async with client:
        # Call MCP tool
        result = await client.call_tool(
            "add",
            {"a": 3, "b": 5}
        )

        print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
