# scripts/

脚本工具集，按职责分目录组织。

```
scripts/
├── build/          构建工具（WASM 编译、OpenUSD 源码同步）
├── generate/       代码生成（AI prompt 模板、SEO prerender、URDF schema）
├── test/           测试入口与测试基础设施
│   ├── browser/      浏览器回归测试（Puppeteer）
│   ├── e2e/          端到端场景测试（Assembly、导入导出、编辑器操作）
│   ├── helpers/      浏览器 / E2E 共用 helper
│   ├── fixtures/     测试 fixture 生成
│   ├── runner/       测试 runner（run-node-tests.mjs / run-all.mjs）
│   ├── setup/        测试语料克隆
│   ├── truth/        真值验证（导入矩阵、格式对比、IsaacSim 基准）
│   ├── benchmark/    性能基准测试（USD 导出耗时）
├── tools/          开发与外部工具
│   ├── dts/          DTS 别名重写
│   ├── google_style_audit.mjs  Google JS/TS + HTML/CSS style 债务审计
│   ├── google_style_baseline.json  Google style 债务 baseline
│   └── isaacsim/     IsaacSim 集成工具（碰撞提取、真值生成、USD 检查）
└── release/        版本管理（bump / show）
```
