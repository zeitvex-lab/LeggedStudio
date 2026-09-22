# 介绍

## 依赖环境

```javascript

node v16+
pnpm 8.7.0

```

## 项目启动

```javascript

// 确保在 src/tools/viz_web目录下

pnpm dev

```

## 项目打包

```javascript

// 确保在 src/tools/viz_web目录下

pnpm build

```

## Typescript Lint 规范检查

```javascript

// 确保在 src/tools/viz_web目录下

pnpm lint

```

## CI/CD

```javascript

// 基于 gitlab，push 之后会自动构建镜像并 push 到公司 docker 仓库

// 如果需要本地打包镜像，可执行命令

docker build -t name .

```
