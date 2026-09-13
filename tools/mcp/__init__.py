"""Legged Studio 自研 MCP server 集合（开发期工具，不进运行时镜像）。

四个 server 共用一个极简 stdio JSON-RPC 骨架（``_rpc.py``），不引第三方 MCP SDK：
控制面 requirements.txt 已经是全仓最轻的那一层，不值得为了开发期工具把它变重。
"""
