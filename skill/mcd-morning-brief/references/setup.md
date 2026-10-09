# 环境配置（麦当劳 MCP + Token）

## 1. 申请 MCP Token（约 2 分钟）

1. 打开 <https://open.mcd.cn/mcp>，右上角【登录】，手机号验证登录
2. 右上角【控制台】→【激活】→ 阅读并同意服务协议
3. 一键复制 **MCP Token**（形如 `1VEo…` 的字符串）

> Token 等同账户凭证：只放环境变量或客户端配置，不要提交进任何仓库、
> 不要贴到聊天/Issue 里。泄露后可回控制台刷新。

## 2. MCP Server 配置

接入地址 `https://mcp.mcd.cn`，Streamable HTTP，Bearer 认证：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

把 `${MCD_MCP_TOKEN}` 替换为实际 Token 后，按下表加入对应客户端：

| 客户端 | 配置入口 |
|---|---|
| ZCode | 技能所在机器直接配 MCP：`~/.zcode/` 下 MCP 配置，或项目 `.mcp.json` |
| WorkBuddy | 左侧【专家·技能·连接器】→【连接器】→【自定义连接器】→【配置 MCP】→ 粘贴 JSON → 保存并启用 |
| Cursor | `~/.cursor/mcp.json` 粘贴上述 JSON |
| Trae | 设置 → MCP → 手动添加 → 粘贴 JSON |
| Cherry Studio | 设置 → MCP → 添加 → 从 JSON 导入 |
| Claude Code | 项目根 `.mcp.json`，或 `claude mcp add` |

## 3. 路径 B（脚本）的运行条件

```bash
pip install "mcp>=1.9"            # 官方 MCP Python SDK（1.x 与 2.x 均兼容）
export MCD_MCP_TOKEN=你的Token    # Windows PowerShell: $env:MCD_MCP_TOKEN="你的Token"
python scripts/brief.py           # 生成今天的晨报（Markdown）
python scripts/brief.py --demo    # 无 Token 离线演示
```

限流：每 Token 600 次/分钟；一次晨报仅调用 6 个工具，正常使用远低于限制。
错误码：401=Token 无效/过期（回控制台重新复制）；403=未携带 Token；429=限流稍后再试。
